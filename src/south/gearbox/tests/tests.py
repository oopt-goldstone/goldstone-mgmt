import unittest
from unittest import mock
from goldstone.south.gearbox.interfaces import InterfaceServer
from goldstone.south.gearbox.gearbox import GearboxServer
import sysrepo
import libyang
import asyncio
import logging
import os
import json
import time
import itertools
from goldstone.lib.core import ServerBase
from concurrent.futures import ProcessPoolExecutor
from taish import NetIf

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)

DEFAULT_MTU = 10000


async def to_subprocess(func):
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=1)
    return await loop.run_in_executor(executor, func)


def test_monitor():
    def cb(a, b, c, d):
        logger.info(b.print_dict())

    conn = sysrepo.SysrepoConnection()
    with conn.start_session() as sess:
        sess.subscribe_notification_tree(
            "goldstone-interfaces",
            "/goldstone-interfaces:*",
            0,
            0,
            cb,
        )

        time.sleep(5)


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.replace_config({}, "goldstone-gearbox")
            sess.apply_changes()

        def noop():
            pass

        taish = mock.AsyncMock()
        taish.close = noop
        module = taish.get_module.return_value

        self.set_logs = []

        async def set_(*args):
            self.set_logs.append(args)

        async def get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                return "(nil)"
            elif args[0] == "pcs-status":
                return ["ready"]
            elif args[0] == "tx-dis":
                return "true"
            elif args[0] == "fec-type":
                return "none"
            elif args[0] == "signal-rate":
                return "100-gbe"
            elif args[0] == "oper-status":
                return "ready"
            elif args[0] == "mtu":
                return DEFAULT_MTU
            elif args[0] == "index":
                return 0
            else:
                return mock.MagicMock()

        async def get_attribute_capability(*args, **kwargs):
            m = mock.MagicMock()
            m.min = ""
            m.max = ""
            if args[0] == "tx-dis":
                m.default_value = "false"
            elif args[0] == "fec-type":
                m.default_value = "none"
            return m

        async def get_attribute_metadata(*args, **kwargs):
            m = mock.MagicMock()
            m.short_name = "pcs-status"
            return m

        async def monitor(*args, **kwargs):
            logger.debug("monitoring..")
            await asyncio.sleep(1)

            obj = mock.MagicMock(spec=NetIf)
            obj.obj = mock.MagicMock()
            obj.obj.module_oid = 1
            obj.get = get
            obj.get_attribute_metadata = get_attribute_metadata

            msg = mock.MagicMock()
            attr = mock.MagicMock()
            attr.value = '["ready"]'
            msg.attrs = [attr]
            await args[1](obj, None, msg)

            await asyncio.sleep(1)

            attr.value = '["ready", "rx-remote-fault"]'
            msg.attrs = [attr]
            await args[1](obj, None, msg)

        module.monitor = monitor
        module.get = get
        module.set = set_
        module.oid = 1

        taish.list.return_value = {"1": module}

        obj = mock.AsyncMock()
        obj.monitor = monitor
        obj.get = get
        obj.set = set_
        obj.get_attribute_capability = get_attribute_capability
        obj.index = 0

        def f(*args):
            return obj

        module.get_netif = f
        module.get_hostif = f

        module.obj.hostifs = [obj]
        module.obj.netifs = [obj]

        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        self.patchers = [
            mock.patch("taish.AsyncClient", return_value=taish),
        ]

        [p.start() for p in self.patchers]

    async def test_basic(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = InterfaceServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                v = sess.get_data("/goldstone-interfaces:interfaces/interface/name")
                v = libyang.xpath_get(v, "interfaces/interface/name")
                self.assertEqual(v, ["Ethernet1/0/1", "Ethernet1/1/1"])
                v = sess.get_data("/goldstone-interfaces:interfaces/interface")
                self.assertEqual(
                    v["interfaces"]["interface"]["Ethernet1/0/1"][
                        "component-connection"
                    ]["platform"]["component"],
                    "port1",
                )
                self.assertEqual(
                    v["interfaces"]["interface"]["Ethernet1/1/1"][
                        "component-connection"
                    ]["transponder"]["module"],
                    "piu1",
                )
                self.assertEqual(
                    v["interfaces"]["interface"]["Ethernet1/1/1"][
                        "component-connection"
                    ]["transponder"]["host-interface"],
                    "0",
                )

        tasks.append(asyncio.to_thread(test))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        await self.server.stop()

    async def test_reconcile(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        gbserver = GearboxServer(self.conn, ifserver)

        self.set_logs = []

        await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("admin-status", "up"),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
            ],
        )

        gbserver.stop()
        gbserver = GearboxServer(self.conn, ifserver)

        self.set_logs = []

        def setup():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1"
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/admin-status",
                    "DOWN",
                )
                sess.apply_changes()

        await asyncio.to_thread(setup)

        await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("admin-status", "down"),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
            ],
        )
        gbserver.stop()
        gbserver = GearboxServer(self.conn, ifserver)

        self.set_logs = []

        def setup():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1"
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/admin-status",
                    "UP",
                )
                sess.apply_changes()

        await asyncio.to_thread(setup)

        await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("admin-status", "up"),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
            ],
        )

        gbserver.stop()
        gbserver = GearboxServer(self.conn, ifserver)

        self.set_logs = []

        def setup():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
                    "Ethernet1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
                    "UP",
                )
                sess.apply_changes()

        await asyncio.to_thread(setup)

        await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("admin-status", "up"),
                ("tx-dis", "false"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("tx-dis", "true"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
            ],
        )

    async def test_fec(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.delete_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/fec",
                    "RS",
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.delete_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        [task.cancel() for task in tasks]

        await ifserver.stop()

    async def test_mtu(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.apply_changes()

            with self.conn.start_session("running") as sess:
                data = sess.get_data(
                    "/goldstone-interfaces:interfaces", include_implicit_defaults=True
                )
                self.assertEqual(len(data["interfaces"]["interface"]), 1)
                data = list(data["interfaces"]["interface"])[0]
                self.assertEqual(data["ethernet"]["config"]["mtu"], DEFAULT_MTU)

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Ethernet1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu",
                    20000,
                )

                sess.apply_changes()

            with self.conn.start_session("running") as sess:
                data = sess.get_data(
                    "/goldstone-interfaces:interfaces", include_implicit_defaults=True
                )
                self.assertEqual(len(data["interfaces"]["interface"]), 1)
                data = list(data["interfaces"]["interface"])[0]
                self.assertEqual(data["ethernet"]["config"]["mtu"], 20000)

        await asyncio.to_thread(test)

        [task.cancel() for task in tasks]

        await ifserver.stop()

    async def test_monitor(self):
        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        tasks.append(asyncio.create_task(to_subprocess(test_monitor)))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def asyncTearDown(self):
        [p.stop() for p in self.patchers]
        self.conn.disconnect()
