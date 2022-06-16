import unittest
import libyang
import asyncio
import logging
import time
import itertools
from multiprocessing import Process, Queue

from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector import create_server_connector
from goldstone.lib.errors import *
from goldstone.lib.util import call
from goldstone.lib.core import *


from goldstone.xlate.openconfig.interfaces import InterfaceServer


class MockGSInterfaceServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-interfaces")
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": NoOp,
                        "name": NoOp,
                        "description": NoOp,
                        "loopback-mode": NoOp,
                        "prbs-mode": NoOp,
                    },
                    "ethernet": NoOp,
                    "switched-vlan": NoOp,
                    "component-connection": NoOp,
                }
            }
        }

    def oper_cb(self, xpath, priv):
        interfaces = [
            {
                "name": "Ethernet1_1",
                "state": {"admin-status": "UP", "oper-status": "UP"},
            },
            {
                "name": "Ethernet2_1",
                "state": {"admin-status": "UP", "oper-status": "UP"},
            },
        ]
        return {"interfaces": {"interface": interfaces}}


def run_mock_gs_server(q):
    conn = Connector()
    server = MockGSInterfaceServer(conn)

    async def _main():
        tasks = await server.start()

        async def evloop():
            while True:
                await asyncio.sleep(1)
                try:
                    q.get(False)
                except:
                    pass
                else:
                    return

        tasks.append(evloop())
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t) for t in tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    asyncio.run(_main())
    conn.stop()


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("openconfig-interfaces")
        self.conn.apply()

        self.q = Queue()
        self.process = Process(target=run_mock_gs_server, args=(self.q,))
        self.process.start()
        await asyncio.sleep(2)  # wait for the mock server

        self.server = InterfaceServer(self.conn, reconciliation_interval=1)
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

    async def test_get_ifname(self):
        def test():
            conn = Connector()
            data = conn.get_operational(
                "/openconfig-interfaces:interfaces/interface/name"
            )
            self.assertEqual(data, ["Ethernet1_1", "Ethernet2_1"])

        await asyncio.create_task(asyncio.to_thread(test))

    async def test_set_admin_status(self):
        def test():
            conn = Connector()
            name = "Ethernet1_1"
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                "iana-if-type:ethernetCsmacd",
            )
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "true",
            )
            conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = conn.get_operational(xpath, one=True)
            self.assertEqual(data, "UP")

            name = "Ethernet1_1"
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "false",
            )
            conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = conn.get_operational(xpath, one=True)
            data = libyang.xpath_get(data, xpath)
            self.assertEqual(data, "DOWN")

            name = "Ethernet1_1"
            conn.delete(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
            )
            conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = conn.get_operational(xpath, one=True)
            self.assertEqual(data, "UP")  # the default value of 'enabled' is "true"

        await asyncio.create_task(asyncio.to_thread(test))

    async def test_reconcile(self):
        def test():
            conn = Connector()

            name = "Ethernet1_1"
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                "iana-if-type:ethernetCsmacd",
            )
            conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "true",
            )
            conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = conn.get_operational(xpath, one=True)
            self.assertEqual(data, "UP")

            conn.set(xpath, "DOWN")  # make the configuration inconsistent
            conn.apply()

            time.sleep(2)

            data = conn.get_operational(xpath, one=True)
            self.assertEqual(
                data, "UP"
            )  # the primitive model configuration must become consistent again

        await asyncio.create_task(asyncio.to_thread(test))

    async def asyncTearDown(self):
        await call(self.server.stop)
        [t.cancel() for t in self.tasks]
        self.conn.stop()
        self.q.put(True)
        self.process.join()


if __name__ == "__main__":
    unittest.main()
