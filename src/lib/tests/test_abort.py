import unittest
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
import os
import sys

from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import *


logger = logging.getLogger(__name__)


class InterfaceAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        self.server.apply_called = True
        logger.info("interface admin-status apply")

    def revert(self, user):
        self.server.revert_called = True
        logger.info("interface admin-status revert")


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
                        "loopback-mode": NoOp,
                        "prbs-mode": NoOp,
                    },
                    "ethernet": NoOp,
                    "switched-vlan": NoOp,
                    "component-connection": NoOp,
                },
            }
        }
        self.apply_called = False
        self.revert_called = False


class ModuleAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        raise InvalArgError("testtesttest")


class MockTransponderServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-transponder")
        self.handlers = {
            "modules": {
                "module": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                        "admin-status": ModuleAdminStatusHandler,
                    },
                },
            }
        }


class TestAbort(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()

    async def test_abort(self):

        ifserver = MockInterfaceServer(self.conn)
        xpserver = MockTransponderServer(self.conn)

        tasks = await ifserver.start()
        tasks += await xpserver.start()

        self.assertFalse(ifserver.apply_called)
        self.assertFalse(ifserver.revert_called)

        def test():
            conn = Connector()
            name = "piu1"
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
                "up",
            )

            name = "Ethernet1/1/1"
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                "UP",
            )

            # in sysrepo v2, the changes to the interface model get handled first, then the changes
            # to the transponder model get handled next. The order was opposite in sysrepo v1

            with self.assertRaisesRegex(CallbackFailedError, "testtesttest"):
                conn.apply()

        await asyncio.create_task(asyncio.to_thread(test))

        self.assertTrue(ifserver.apply_called)
        self.assertTrue(ifserver.revert_called)

        ifserver.stop()
        xpserver.stop()

        await asyncio.gather(*tasks)

    async def asyncTearDown(self):
        self.conn.stop()
