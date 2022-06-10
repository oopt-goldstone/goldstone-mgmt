import unittest
import libyang
import asyncio
import logging
import os
import json

from goldstone.south.sonic.interfaces import InterfaceServer
from goldstone.lib.connector.sysrepo import Connector


class MockK8S(object):
    def update_usonic_config(self, interface_map):
        return False

    async def run_bcmcmd_port(self, ifname, cmd):
        pass

    def get_default_iftype(self, ifname):
        return "KR4"

    async def bcm_ports_info(self, ports):
        return {}


class MockSONiC(object):
    def __init__(self):
        self.is_rebooting = False
        self.counter_if_dict = {}
        self.notif_if = {}
        self.k8s = MockK8S()
        self.logs = []

    def enable_counters(self):
        pass

    def cache_counters(self):
        pass

    def get_ifnames(self):
        return ["Ethernet1_1", "Ethernet2_1", "Ethernet13_1"]

    def set_config_db(self, ifname, key, value):
        self.logs.append((ifname, key, value))

    def get_counters(self, ifname):
        return {}

    def get_oper_status(self, ifname):
        return "up"

    def hgetall(self, db, key):
        return {}


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-interfaces")
        self.conn.apply()

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.sonic = MockSONiC()
        self.server = InterfaceServer(self.conn, self.sonic, [], platform_info)

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def test_get_ifname(self):
        def test():
            conn = Connector()
            data = conn.get_operational(
                "/goldstone-interfaces:interfaces/interface/name"
            )
            self.assertEqual(len(data), len(self.sonic.get_ifnames()))

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_set_admin_up(self):
        def test():
            conn = Connector()
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

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, pending = await asyncio.wait(
            self.tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            e = task.exception()
            if e:
                raise e

        admin_status = None
        for event in self.sonic.logs:
            if event[0] == "Ethernet1_1" and event[1] == "admin-status":
                admin_status = event[2]

        self.assertEqual(admin_status, "UP")

    async def test_clear_ds(self):
        def test():
            conn = Connector()

            name = "Ethernet1_1"
            prefix = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config"

            conn.set(f"{prefix}/name", name)
            conn.set(f"{prefix}/admin-status", "UP")
            conn.apply()

            self.sonic.logs = []

            async def post(*args):
                user = args[0]
                self.assertFalse(user.get("update-sonic"))

            self.server.post = post

            conn.delete_all("goldstone-interfaces")
            conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_get_default(self):
        self.assertFalse(self.server.get_default("enabled"))

    async def test_component_connection(self):
        def test():
            conn = Connector()
            data = conn.get_operational(
                "/goldstone-interfaces:interfaces/interface[name='Ethernet1_1']",
                one=True,
            )
            self.assertEqual(
                data["component-connection"]["platform"]["component"], "port1"
            )

            data = conn.get_operational(
                "/goldstone-interfaces:interfaces/interface[name='Ethernet13_1']",
                one=True,
            )
            self.assertEqual(
                data["component-connection"]["transponder"]["module"], "piu1"
            )
            self.assertEqual(
                data["component-connection"]["transponder"]["host-interface"], "0"
            )

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.sonic.logs = []
        self.conn.stop()


if __name__ == "__main__":
    unittest.main()
