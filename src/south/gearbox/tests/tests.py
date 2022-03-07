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
from taish import HostIf
import base64

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)

DEFAULT_MTU = 10000


async def to_subprocess(func):
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=1)
    return await loop.run_in_executor(executor, func)


def test_monitor():
    def cb(xpath, notif_type, value, timestamp, priv):
        logger.info(f"{xpath=}, {notif_type=}, {value=}, {timestamp=}, {priv=}")

    conn = sysrepo.SysrepoConnection()
    with conn.start_session() as sess:
        sess.subscribe_notification(
            "goldstone-interfaces",
            "/goldstone-interfaces:*",
            cb,
        )

        time.sleep(5)


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-gearbox")
            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

        taish = mock.AsyncMock()

        self.set_logs = []

        async def set_(*args):
            self.set_logs.append(args)

        async def set_multiple(*args):
            for a in args[0]:
                self.set_logs.append(a)

        async def module_get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                return "(nil)"
            elif args[0] == "oper-status":
                return "ready"
            elif args[0] == "admin-status":
                return "up"
            elif args[0] == "tributary-mapping":
                return '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]'

        async def get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                return "(nil)"
            elif args[0] == "pcs-status":
                if kwargs.get("json"):
                    return '["ready", "block-locked"]'
                else:
                    return ["ready"]
            elif args[0] == "tx-dis":
                return "true"
            elif args[0] == "fec-type":
                return "none"
            elif args[0] == "signal-rate":
                return "100-gbe"
            elif args[0] == "oper-status":
                return "up"
            elif args[0] == "admin-status":
                return "up"
            elif args[0] == "mtu":
                return DEFAULT_MTU
            elif args[0] == "mru":
                return DEFAULT_MTU
            elif args[0] == "index":
                return 0
            elif args[0] == "serdes-status":
                if kwargs.get("json"):
                    return '["tx-ready", "rx-ready"]'
                else:
                    return ["tx-ready", "rx-ready"]
            elif args[0] == "anlt-defect":
                return '["resolved", "completed"]'
            elif args[0] == "auto-negotiation":
                return "true"
            elif args[0] == "macsec-static-key":
                return "50462976,117835012,185207048,252579084"
            elif args[0] == "macsec-ingress-sa-stats":
                return ",".join(str(i) for i in range(10))
            elif args[0] == "macsec-egress-sa-stats":
                return ",".join(str(i) for i in range(4))
            elif args[0] == "macsec-ingress-secy-stats":
                return ",".join(str(i) for i in range(20))
            elif args[0] == "macsec-egress-secy-stats":
                return ",".join(str(i) for i in range(15))
            elif args[0] == "macsec-ingress-channel-stats":
                return ",".join(str(i) for i in range(7))
            elif args[0] == "macsec-egress-channel-stats":
                return ",".join(str(i) for i in range(7))
            elif args[0] == "pmon-enet-mac-rx":
                return ",".join(str(i) for i in range(40))
            elif args[0] == "pmon-enet-mac-tx":
                return ",".join(str(i) for i in range(33))
            elif args[0] == "pmon-enet-phy-rx":
                return ",".join(str(i) for i in range(109))
            elif args[0] == "tx-timing-mode":
                return "synce-ref-clk"
            elif args[0] == "current-tx-timing-mode":
                return "synce-ref-clk"
            else:
                return mock.MagicMock()

        async def get_multiple(*args, **kwargs):
            return [await get(name, **kwargs) for name in args[0]]

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
            logger.debug(f"monitoring.. {args}, {kwargs}")
            await asyncio.sleep(1)

            obj = mock.MagicMock(spec=NetIf(None, None, None))
            obj.obj = mock.MagicMock()
            obj.obj.module_oid = 1
            obj.get = get
            obj.get_attribute_metadata = get_attribute_metadata

            msg = mock.MagicMock()
            attr = mock.MagicMock()
            attr.value = "up"
            msg.attrs = [attr]
            await args[1](obj, None, msg)

            await asyncio.sleep(1)

            attr.value = "down"
            msg.attrs = [attr]
            await args[1](obj, None, msg)

            await asyncio.sleep(1)

        def f(oid, spec):
            obj = mock.AsyncMock(spec=spec)
            obj.monitor = monitor
            obj.get = get
            obj.set = set_
            obj.set_multiple = set_multiple
            obj.get_multiple = get_multiple
            obj.get_attribute_capability = get_attribute_capability
            obj.index = 0
            obj.oid = oid
            return obj

        def get_netif(*args):
            return f(0x3000000010000, NetIf(None, None, None))

        def get_hostif(*args):
            return f(0x2000000010000, HostIf(None, None, None))

        module = taish.get_module.return_value
        module.monitor = monitor
        module.get = module_get
        module.set = set_
        module.oid = 1
        module.get_netif = get_netif
        module.get_hostif = get_hostif
        module.obj.location = "1"
        module.obj.netifs = [get_netif()]
        module.obj.hostifs = [get_hostif()]
        module.netifs = [get_netif()]
        module.hostifs = [get_hostif()]

        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        taish.list.return_value = {"1": module}

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
                self.assertEqual(v, ["Interface1/0/1", "Interface1/1/1"])
                v = sess.get_data("/goldstone-interfaces:interfaces/interface")
                self.assertEqual(
                    v["interfaces"]["interface"]["Interface1/0/1"]["state"][
                        "associated-gearbox"
                    ],
                    "1",
                )
                self.assertEqual(
                    v["interfaces"]["interface"]["Interface1/0/1"][
                        "component-connection"
                    ]["platform"]["component"],
                    "port1",
                )
                self.assertEqual(
                    v["interfaces"]["interface"]["Interface1/1/1"][
                        "component-connection"
                    ]["transponder"]["module"],
                    "piu1",
                )
                self.assertEqual(
                    v["interfaces"]["interface"]["Interface1/1/1"][
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

        tasks = await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("auto-negotiation", "false"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("macsec-static-key", ""),
                ("tributary-mapping", "[]"),
                ("admin-status", "up"),
            ],
        )

        gbserver.stop()
        await asyncio.gather(*tasks)
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

        tasks = await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("auto-negotiation", "false"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("macsec-static-key", ""),
                ("tributary-mapping", "[]"),
                ("admin-status", "down"),
            ],
        )
        gbserver.stop()
        asyncio.gather(*tasks)
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

        tasks = await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("auto-negotiation", "false"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("macsec-static-key", ""),
                ("tributary-mapping", "[]"),
                ("admin-status", "up"),
            ],
        )

        gbserver.stop()
        await asyncio.gather(*tasks)
        gbserver = GearboxServer(self.conn, ifserver)

        self.set_logs = []

        def setup():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status",
                    "UP",
                )
                sess.apply_changes()

        await asyncio.to_thread(setup)

        tasks = await gbserver.start()

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "normal"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("auto-negotiation", "false"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("fec-type", "rs"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("macsec-static-key", ""),
                ("tributary-mapping", "[]"),
                ("admin-status", "up"),
            ],
        )

        gbserver.stop()
        await asyncio.gather(*tasks)

    async def test_fec(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Interface1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Interface1/0/1"
                sess.delete_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                ifname = "Interface1/0/1"
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
                ifname = "Interface1/0/1"
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
                ifname = "Interface1/0/1"
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
                ifname = "Interface1/0/1"
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                    ifname,
                )
                sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu",
                    9000,
                )

                sess.apply_changes()

            with self.conn.start_session("running") as sess:
                data = sess.get_data(
                    "/goldstone-interfaces:interfaces", include_implicit_defaults=True
                )
                self.assertEqual(len(data["interfaces"]["interface"]), 1)
                data = list(data["interfaces"]["interface"])[0]
                self.assertEqual(data["ethernet"]["config"]["mtu"], 9000)

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

    async def test_gearbox_oper_cb(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        gbserver = GearboxServer(self.conn, ifserver)

        tasks = await gbserver.start()

        self.set_logs = []  # clear set_logs

        def test_oper_cb():
            with self.conn.start_session("operational") as sess:
                data = sess.get_data("/goldstone-gearbox:gearboxes/gearbox")
                self.assertEqual(len(data["gearboxes"]["gearbox"]), 1)
                data = list(data["gearboxes"]["gearbox"])[0]
                self.assertEqual(data["state"]["admin-status"], "UP")
                self.assertEqual(data["state"]["oper-status"], "UP")
                self.assertEqual(data["state"]["enable-flexible-connection"], False)
                connection = list(data["connections"]["connection"])
                self.assertEqual(len(connection), 1)
                self.assertEqual(connection[0]["client-interface"], "Interface1/0/1")
                self.assertEqual(connection[0]["line-interface"], "Interface1/1/1")

        await asyncio.to_thread(test_oper_cb)
        gbserver.stop()
        await asyncio.gather(*tasks)

    async def test_gearbox_invalid_creation(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        gbserver = GearboxServer(self.conn, ifserver)

        tasks = await gbserver.start()

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='10']/config/name", "10"
                )
                with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                    sess.apply_changes()

        await asyncio.to_thread(test)
        gbserver.stop()
        await asyncio.gather(*tasks)

    async def test_gearbox_enable_flexible_connection(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        gbserver = GearboxServer(self.conn, ifserver)

        tasks = await gbserver.start()

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1"
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                    True,
                )
                sess.apply_changes()
                self.assertTrue("tributary-mapping" in (v[0] for v in self.set_logs))
                self.set_logs = []  # clear set_logs
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                    False,
                )
                sess.apply_changes()
                self.assertTrue("tributary-mapping" in (v[0] for v in self.set_logs))

        await asyncio.to_thread(test)
        gbserver.stop()
        await asyncio.gather(*tasks)

    async def test_gearbox_create_connection(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        gbserver = GearboxServer(self.conn, ifserver)

        tasks = await gbserver.start()

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1"
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                    True,
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                    "Interface1/1/1",
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/connections/connection[client-interface='Interface1/0/1'][line-interface='Interface1/1/1']/config/client-interface",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-gearbox:gearboxes/gearbox[name='1']/connections/connection[client-interface='Interface1/0/1'][line-interface='Interface1/1/1']/config/line-interface",
                    "Interface1/1/1",
                )
                sess.apply_changes()

        await asyncio.to_thread(test)
        gbserver.stop()
        await asyncio.gather(*tasks)

    async def test_interface_otn(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/interface-type",
                    "IF_OTN",
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("signal-rate", "otu4"),
                ("provision-mode", "none"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("fec-type", "rs"),
                ("auto-negotiation", "false"),
                ("tx-timing-mode", "auto"),
            ],
        )

    async def test_interface_macsec(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        self.set_logs = []  # clear set_logs
        key = base64.b64encode(bytearray(list(range(16)))).decode()

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                    "Interface1/1/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/ethernet/goldstone-static-macsec:static-macsec/config/key",
                    key,
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("macsec-static-key", "50462976,117835012,185207048,252579084"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("fec-type", "rs"),
                ("tx-timing-mode", "auto"),
            ],
        )

        def test():
            with self.conn.start_session("operational") as sess:
                xpath = (
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']"
                )
                v = sess.get_data(xpath)
                v = libyang.xpath_get(v, xpath)
                self.assertTrue("static-macsec" in v["ethernet"])
                self.assertEqual(v["ethernet"]["static-macsec"]["state"]["key"], key)

        await asyncio.to_thread(test)

    async def test_interface_auto_nego(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/ethernet/auto-negotiate/config/enabled",
                    "true",
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("auto-negotiation", "true"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("tx-timing-mode", "auto"),
            ],
        )

        def test():
            with self.conn.start_session("operational") as sess:
                xpath = (
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                )
                v = sess.get_data(xpath)
                v = libyang.xpath_get(v, xpath)
                self.assertEqual(
                    v["ethernet"]["auto-negotiate"]["state"]["status"],
                    ["resolved", "completed"],
                )

        await asyncio.to_thread(test)

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                    "Interface1/1/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/ethernet/auto-negotiate/config/enabled",
                    "true",
                )

                # enabling auto nego is not supported for line side interface
                with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                    sess.apply_changes()

        await asyncio.to_thread(test)

    async def test_interface_tx_timing_mode(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await ifserver.start())

        self.set_logs = []  # clear set_logs

        def test():
            with self.conn.start_session("running") as sess:
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                    "Interface1/0/1",
                )
                sess.set_item(
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/ethernet/goldstone-synce:synce/config/tx-timing-mode",
                    "synce-ref-clk",
                )
                sess.apply_changes()

        await asyncio.to_thread(test)

        self.assertEqual(
            self.set_logs,
            [
                ("provision-mode", "none"),
                ("provision-mode", "none"),
                ("signal-rate", "100-gbe"),
                ("tx-timing-mode", "synce-ref-clk"),
                ("mtu", DEFAULT_MTU),
                ("mru", DEFAULT_MTU),
                ("fec-type", "rs"),
                ("auto-negotiation", "false"),
            ],
        )

        def test():
            with self.conn.start_session("operational") as sess:
                xpath = (
                    "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                )
                v = sess.get_data(xpath)
                v = libyang.xpath_get(v, xpath)
                self.assertEqual(
                    v["ethernet"]["synce"]["state"],
                    {
                        "tx-timing-mode": "synce-ref-clk",
                        "current-tx-timing-mode": "synce-ref-clk",
                    },
                )

        await asyncio.to_thread(test)

    async def asyncTearDown(self):
        [p.stop() for p in self.patchers]
        self.conn.disconnect()
