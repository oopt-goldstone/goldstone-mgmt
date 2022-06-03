import unittest
from unittest import mock
import sysrepo
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
import itertools
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
import os
import json
import sys


logger = logging.getLogger(__name__)


class InterfaceAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        raise Exception("error")


class ModuleAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        self.server.apply_called = True
        logger.info("module admin-status apply")

    def revert(self, user):
        self.server.revert_called = True
        logger.info("module admin-status revert")


class MockInterfaceServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-interfaces")
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                        "admin-status": InterfaceAdminStatusHandler,
                    },
                    "ethernet": NoOp,
                    "switched-vlan": NoOp,
                    "component-connection": NoOp,
                },
            }
        }


class MockTransponderServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-transponder")
        self.handlers = {
            "modules": {
                "module": {
                    "name": NoOp,
                    "config": {"name": NoOp, "admin-status": ModuleAdminStatusHandler},
                },
            }
        }
        self.apply_called = False
        self.revert_called = False


class TestAbort(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.replace_config({}, "goldstone-transponder")
            sess.apply_changes()

    async def test_abort(self):

        ifserver = MockInterfaceServer(self.conn)
        xpserver = MockTransponderServer(self.conn)

        servers = [ifserver, xpserver]

        tasks = list(
            asyncio.create_task(c)
            for c in itertools.chain.from_iterable([await s.start() for s in servers])
        )

        self.assertFalse(xpserver.apply_called)
        self.assertFalse(xpserver.revert_called)

        def test():

            with self.conn.start_session() as sess:
                name = "piu1"
                sess.set_item(
                    f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
                    "up",
                )

                name = "Ethernet1/1/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                    "UP",
                )
                with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                    sess.apply_changes()

        await asyncio.create_task(asyncio.to_thread(test))

        self.assertTrue(xpserver.apply_called)
        self.assertTrue(xpserver.revert_called)

        ifserver.stop()
        xpserver.stop()

        await asyncio.gather(*tasks)
