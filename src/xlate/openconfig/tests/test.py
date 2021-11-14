import unittest
from goldstone.xlate.openconfig.interfaces import InterfaceServer
from goldstone.lib.core import *
import sysrepo
import libyang
import asyncio
import logging
import time
import itertools
from multiprocessing import Process, Queue


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
                    },
                    "ethernet": NoOp,
                    "switched-vlan": NoOp,
                    "component-connection": NoOp,
                }
            }
        }

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
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
    conn = sysrepo.SysrepoConnection()
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


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.replace_config({}, "openconfig-interfaces")
            sess.apply_changes()

        self.server = InterfaceServer(self.conn, reconciliation_interval=1)
        self.q = Queue()
        self.process = Process(target=run_mock_gs_server, args=(self.q,))
        self.process.start()

        servers = [self.server]

        self.tasks = list(
            itertools.chain.from_iterable([await s.start() for s in servers])
        )

    async def test_get_ifname(self):
        def test():
            time.sleep(2)  # wait for the mock server
            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                data = sess.get_data("/openconfig-interfaces:interfaces")
                data = libyang.xpath_get(
                    data, "/openconfig-interfaces:interfaces/interface/name"
                )
                self.assertEqual(data, ["Ethernet1_1", "Ethernet2_1"])

        self.tasks.append(asyncio.to_thread(test))
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t)
            for t in self.tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_set_admin_status(self):
        def test():
            time.sleep(2)  # wait for the mock server

            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                name = "Ethernet1_1"
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                    "iana-if-type:ethernetCsmacd",
                )
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                    "true",
                )
                sess.apply_changes()

                xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
                data = sess.get_data(xpath)
                data = libyang.xpath_get(data, xpath)
                self.assertEqual(data, "UP")

            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                name = "Ethernet1_1"
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                    "false",
                )
                sess.apply_changes()

                xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
                data = sess.get_data(xpath)
                data = libyang.xpath_get(data, xpath)
                self.assertEqual(data, "DOWN")

            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                name = "Ethernet1_1"
                sess.delete_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                )
                sess.apply_changes()

                xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
                data = sess.get_data(xpath)
                data = libyang.xpath_get(data, xpath)
                self.assertEqual(data, "UP")  # the default value of 'enabled' is "true"

        self.tasks.append(asyncio.to_thread(test))
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t)
            for t in self.tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_reconcile(self):
        def test():
            time.sleep(2)  # wait for the mock server

            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                name = "Ethernet1_1"
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                    "iana-if-type:ethernetCsmacd",
                )
                sess.set_item(
                    f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                    "true",
                )
                sess.apply_changes()

                xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
                data = sess.get_data(xpath)
                data = libyang.xpath_get(data, xpath)
                self.assertEqual(data, "UP")

                sess.set_item(xpath, "DOWN")  # make the configuration inconsistent
                sess.apply_changes()

                time.sleep(2)

                data = sess.get_data(xpath)
                data = libyang.xpath_get(data, xpath)
                self.assertEqual(
                    data, "UP"
                )  # the primitive model configuration must become consistent again

        self.tasks.append(asyncio.to_thread(test))
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t)
            for t in self.tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def asyncTearDown(self):
        await self.server.stop()
        self.tasks = []
        self.conn.disconnect()
        self.q.put(True)
        self.process.join()


if __name__ == "__main__":
    unittest.main()
