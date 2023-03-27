import unittest
from unittest import mock
import itertools
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor

from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import *


fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)


class InterfaceAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        logger.info("interface admin-status apply")
        self.server.count += 1


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
        self.count = 0


class ModuleAdminStatusHandler(ChangeHandler):
    def apply(self, user):
        logger.info("module admin-status apply")
        self.server.count += 1


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
        self.count = 0


async def to_subprocess(func):
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=1)
    return await loop.run_in_executor(executor, func)


def update_if():
    conn = Connector()
    for _ in range(100):
        conn.delete_all("goldstone-interfaces")
        conn.apply()

        name = "Ethernet1_1"
        conn.set(
            f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
            name,
        )
        conn.set(
            f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
            "UP",
        )
        conn.apply()


def update_xp():
    conn = Connector()
    for _ in range(100):
        conn.delete_all("goldstone-transponder")
        conn.apply()

        name = "piu1"
        conn.set(
            f"/goldstone-transponder:modules/module[name='{name}']/config/name",
            name,
        )
        conn.set(
            f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
            "up",
        )
        conn.apply()


class TestConcurrentAccess(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()

    async def test_concurrent_update(self):
        if_server = MockInterfaceServer(self.conn)
        xp_server = MockTransponderServer(self.conn)

        servers = [if_server, xp_server]

        tasks = list(
            asyncio.create_task(c)
            for c in itertools.chain.from_iterable([await s.start() for s in servers])
        )

        await asyncio.gather(
            to_subprocess(update_if),
            to_subprocess(update_xp),
        )

        self.assertEqual(if_server.count, 199)
        self.assertEqual(xp_server.count, 199)

        if_server.stop()
        xp_server.stop()

        await asyncio.gather(*tasks)

    async def asyncTearDown(self):
        self.conn.stop()
