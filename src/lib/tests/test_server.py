import unittest
import logging
import asyncio

from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import *


class Handler(ChangeHandler):
    def apply(self, user):
        self.server.handled_changes.append(self.change)


class Server(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-interfaces")
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                        "admin-status": Handler,
                        "loopback-mode": Handler,
                        "prbs-mode": Handler,
                    },
                    "ethernet": {"auto-negotiate": {"config": {"enabled": Handler}}},
                }
            }
        }
        # changes that are handled by Handler
        self.handled_changes = []


class TestServerBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-interfaces")
        self.conn.apply()

        self.server = Server(self.conn)
        v = await self.server.start()
        self.assertTrue(len(v), 1)
        self.stop_event = v[0]

    async def asyncTearDown(self):
        self.server.stop()
        await self.stop_event

    async def test_basic_change_handling(self):
        def t():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='1']/config/name", 1
            )
            conn.apply()

            # leaves that have a default value must be handled.
            # admin-status, loopback-mode, prbs-mode, ethernet/auto-negotiate/config/enabled
            self.assertEqual(len(self.server.handled_changes), 4)

        await asyncio.create_task(asyncio.to_thread(t))

    async def test_unsupported_change_handling(self):
        def t():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='1']/config/name", 1
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='1']/config/interface-type",
                "IF_ETHERNET",
            )

            with self.assertRaises(CallbackFailedError):
                conn.apply()

            self.assertEqual(len(self.server.handled_changes), 0)

        await asyncio.create_task(asyncio.to_thread(t))
