import unittest
from goldstone.south.sonic.interfaces import InterfaceServer
import sysrepo
import asyncio
import logging


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
        return ["Ethernet1_1", "Ethernet2_1"]

    def set_config_db(self, ifname, key, value):
        self.logs.append((ifname, key, value))

    def get_counters(self, ifname):
        pass

    def get_oper_status(self, ifname):
        return "up"

    def hgetall(self, db, key):
        return {}


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

        self.sonic = MockSONiC()
        self.server = InterfaceServer(self.conn, self.sonic, [])

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def test_get_ifname(self):
        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                data = sess.get_data("/goldstone-interfaces:interfaces/interface/name")
                self.assertEqual(
                    len(data["interfaces"]["interface"]), len(self.sonic.get_ifnames())
                )

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_set_admin_up(self):
        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                name = "Ethernet1_1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                    "UP",
                )
                sess.apply_changes()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        admin_status = None
        for event in self.sonic.logs:
            if event[0] == "Ethernet1_1" and event[1] == "admin-status":
                admin_status = event[2]

        self.assertEqual(admin_status, "UP")

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.sonic.logs = []
        self.conn.disconnect()


if __name__ == "__main__":
    unittest.main()
