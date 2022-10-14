import unittest
from unittest import mock
import asyncio
import logging
import os
import json
import time
import base64
import struct

from taish import NetIf, HostIf, Module

from goldstone.lib.core import ServerBase
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector import create_server_connector
from goldstone.lib.errors import *
from goldstone.lib.util import call

from goldstone.south.gearbox.interfaces import InterfaceServer
from goldstone.south.gearbox.gearbox import GearboxServer


fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)

DEFAULT_MTU = 10000


class TestInterfaceServerMethods(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()
        self.server = InterfaceServer(self.conn, "", platform_info)

    def test_get_default(self):
        v = self.server.get_default("admin-status", "")
        self.assertEqual(v, "DOWN")


class TestBase(unittest.IsolatedAsyncioTestCase):
    def patch_taish(self):
        async def set_(oid, *args):
            logs = self.set_logs.get(oid, {})
            logs[args[0]] = args[1]
            self.set_logs[oid] = logs

        async def set_multiple(*args, oid):
            for a in args[0]:
                logs = self.set_logs.get(oid, {})
                logs[a[0]] = a[1]
                self.set_logs[oid] = logs

        async def module_get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                return "(nil)"
            elif args[0] == "oper-status":
                return "ready"
            elif args[0] == "admin-status":
                return "up"
            elif args[0] == "tributary-mapping":
                return '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]'
            elif args[0] == "pgmrclk-assignment":
                if kwargs.get("json"):
                    return '["oid:0x2000000010000", "oid:0x3000000010000"]'
                else:
                    return "oid:0x2000000010000,oid:0x3000000010000"
            elif args[0] == "num-pgmrclk":
                return "4"

        async def get(spec, *args, **kwargs):
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
            elif args[0] == "loopback-mode":
                return "shallow"
            elif args[0] == "prbs-mode":
                return "prbs31"
            elif args[0] == "current-prbs-ber":
                return "1.200000e-03"
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
            elif args[0] == "pin-mode":
                if isinstance(spec, NetIf):
                    return "pam4"
                else:
                    return "nrz"
            else:
                return mock.MagicMock()

        async def get_multiple(spec, *args, **kwargs):
            return [await get(spec, name, **kwargs) for name in args[0]]

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
            #            m.short_name = "pcs-status"
            m.short_name = "oper-status"
            return m

        async def get_attribute_capability(*args, **kwargs):
            m = mock.MagicMock()
            m.min = ""
            m.max = ""
            return m

        async def monitor(spec, *args, **kwargs):
            logger.debug(f"monitoring.. {args}, {kwargs}")
            await asyncio.sleep(1)

            obj = mock.MagicMock(spec=NetIf(None, None, None))
            obj.obj = mock.MagicMock()
            obj.obj.module_oid = 1
            obj.get = lambda *args, **kwargs: get(spec, *args, **kwargs)
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
            obj.monitor = lambda *args, **kwargs: monitor(spec, *args, **kwargs)
            obj.get = lambda *args, **kwargs: get(spec, *args, **kwargs)
            obj.set = lambda *args: set_(oid, *args)
            obj.set_multiple = lambda *args: set_multiple(*args, oid=oid)
            obj.get_multiple = lambda *args, **kwargs: get_multiple(
                spec, *args, **kwargs
            )
            obj.get_attribute_capability = get_attribute_capability
            obj.index = 0
            obj.oid = oid
            return obj

        def get_netif(*args):
            return f(0x3000000010000, NetIf(None, None, None))

        def get_hostif(*args):
            return f(0x2000000010000, HostIf(None, None, None))

        module = mock.AsyncMock(spec=Module(None, None))
        module.monitor = monitor
        module.get = module_get
        module.set = lambda *args: set_(0x1, *args)
        module.set_multiple = lambda *args: set_multiple(*args, oid=0x1)
        module.get_multiple = lambda *args, **kwargs: get_multiple(
            Module(None, None), *args, **kwargs
        )
        module.oid = 0x1
        module.get_netif = get_netif
        module.get_hostif = get_hostif
        module.get_attribute_capability = get_attribute_capability
        module.location = "1"
        module.netifs = [get_netif()]
        module.hostifs = [get_hostif()]

        module.obj = mock.AsyncMock()
        module.obj.location = "1"
        module.obj.netifs = [get_netif()]
        module.obj.hostifs = [get_hostif()]

        taish = mock.AsyncMock()
        taish.get_module.return_value = module
        taish.list.return_value = {"1": module}

        self.patchers = [
            mock.patch("taish.AsyncClient", return_value=taish),
        ]

        [p.start() for p in self.patchers]

    async def asyncTearDown(self):
        [p.stop() for p in self.patchers]
        await call(self.server.stop)
        [t.cancel() for t in self.tasks]
        self.conn.stop()


class TestInterfaceServer(TestBase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-gearbox")
        self.conn.delete_all("goldstone-interfaces")
        self.conn.apply()

        self.set_logs = {}

        self.patch_taish()

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = InterfaceServer(self.conn, "", platform_info)
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

    async def test_basic(self):
        def test():
            conn = Connector()
            v = conn.get_operational("/goldstone-interfaces:interfaces/interface/name")
            self.assertEqual(v, ["Interface1/0/1", "Interface1/1/1"])
            v = conn.get_operational("/goldstone-interfaces:interfaces/interface")
            self.assertEqual(
                v["Interface1/0/1"]["state"]["associated-gearbox"],
                "1",
            )
            self.assertEqual(
                v["Interface1/0/1"]["component-connection"]["platform"]["component"],
                "port1",
            )
            self.assertEqual(
                v["Interface1/1/1"]["component-connection"]["transponder"]["module"],
                "piu1",
            )
            self.assertEqual(
                v["Interface1/1/1"]["component-connection"]["transponder"][
                    "host-interface"
                ],
                "0",
            )

        await asyncio.create_task(asyncio.to_thread(test))

    async def test_fec(self):
        def test():
            conn = Connector()
            ifname = "Interface1/0/1"
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            conn.apply()

        await asyncio.to_thread(test)

        def test():
            conn = Connector()
            ifname = "Interface1/0/1"
            conn.delete(f"/goldstone-interfaces:interfaces/interface[name='{ifname}']")
            conn.apply()

        await asyncio.to_thread(test)

        def test():
            conn = Connector()
            ifname = "Interface1/0/1"
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/fec",
                "RS",
            )
            conn.apply()

        await asyncio.to_thread(test)

        def test():
            conn = Connector()
            ifname = "Interface1/0/1"
            conn.delete(f"/goldstone-interfaces:interfaces/interface[name='{ifname}']")
            conn.apply()

        await asyncio.to_thread(test)

    async def test_mtu(self):
        def test():
            conn = Connector()
            ifname = "Interface1/0/1"
            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            conn.apply()

            data = conn.get(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']",
                include_implicit_defaults=True,
            )
            self.assertEqual(data["ethernet"]["config"]["mtu"], DEFAULT_MTU)

            conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu",
                9000,
            )
            conn.apply()

            data = conn.get(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']",
                include_implicit_defaults=True,
            )
            self.assertEqual(data["ethernet"]["config"]["mtu"], 9000)

        await asyncio.to_thread(test)

    async def test_monitor(self):
        def test():
            def cb(xpath, notif_type, value, timestamp, priv):
                priv.append((xpath, notif_type, value, timestamp))

            conn = Connector()
            sconn = create_server_connector(conn, "goldstone-interfaces")
            priv = []
            sconn.subscribe_notification(
                "goldstone-interfaces", "/goldstone-interfaces:*", cb, priv
            )

            time.sleep(5)
            self.assertEqual(len(priv), 4)
            sconn.stop()
            conn.stop()

        await asyncio.create_task(asyncio.to_thread(test))

    async def test_interface_otn(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/interface-type",
                "IF_OTN",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x2000000010000],
                {
                    "provision-mode": "none",
                    "signal-rate": "otu4",
                    "loopback-type": "none",
                    "prbs-type": "none",
                    "fec-type": "rs",
                    "auto-negotiation": "false",
                    "tx-timing-mode": "auto",
                },
            )

        await asyncio.to_thread(test)

    async def test_interface_macsec(self):
        def test():
            key = base64.b64encode(bytearray(list(range(16)))).decode()
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/ethernet/goldstone-static-macsec:static-macsec/config/key",
                key,
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "none",
                    "prbs-type": "none",
                    "fec-type": "rs",
                    "tx-timing-mode": "auto",
                },
            )
            xpath = "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']"
            v = conn.get_operational(xpath, one=True)
            self.assertTrue("static-macsec" in v["ethernet"])
            self.assertEqual(v["ethernet"]["static-macsec"]["state"]["key"], key)

        await asyncio.to_thread(test)

    async def test_interface_auto_nego(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/ethernet/auto-negotiate/config/enabled",
                "true",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x2000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "none",
                    "prbs-type": "none",
                    "tx-timing-mode": "auto",
                },
            )

            xpath = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
            v = conn.get_operational(xpath, one=True)
            self.assertEqual(
                v["ethernet"]["auto-negotiate"]["state"]["status"],
                ["resolved", "completed"],
            )

            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/ethernet/auto-negotiate/config/enabled",
                "true",
            )

            # enabling auto nego is not supported for line side interface
            with self.assertRaises(CallbackFailedError):
                conn.apply()

        await asyncio.to_thread(test)

    async def test_interface_tx_timing_mode(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/ethernet/goldstone-synce:synce/config/tx-timing-mode",
                "synce-ref-clk",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x2000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "none",
                    "prbs-type": "none",
                    "fec-type": "rs",
                    "auto-negotiation": "false",
                },
            )

            xpath = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
            v = conn.get_operational(xpath, one=True)
            self.assertEqual(
                v["ethernet"]["synce"]["state"],
                {
                    "tx-timing-mode": "synce-ref-clk",
                    "current-tx-timing-mode": "synce-ref-clk",
                },
            )

        await asyncio.to_thread(test)

    async def test_pin_mode(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/pin-mode",
                "PAM4",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "none",
                    "prbs-type": "none",
                    "fec-type": "rs",
                    "tx-timing-mode": "auto",
                },
            )

        await asyncio.to_thread(test)

    async def test_loopback_mode(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/loopback-mode",
                "SHALLOW",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "shallow",
                    "prbs-type": "none",
                    "fec-type": "rs",
                    "tx-timing-mode": "auto",
                },
            )

            self.set_logs = {}  # clear set_logs

            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/loopback-mode",
                "DEEP",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "loopback-type": "deep",
                },
            )

            self.set_logs = {}  # clear set_logs

            conn.delete(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/loopback-mode",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "loopback-type": "none",
                },
            )

        await asyncio.to_thread(test)

    async def test_prbs_mode(self):
        def test():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/prbs-mode",
                "PRBS7",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "provision-mode": "none",
                    "loopback-type": "none",
                    "prbs-type": "prbs7",
                    "fec-type": "rs",
                    "tx-timing-mode": "auto",
                },
            )

            self.set_logs = {}  # clear set_logs

            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/prbs-mode",
                "PRBS31",
            )
            conn.apply()

            v = conn.get_operational(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/state/current-prbs-ber",
                one=True,
            )
            v = struct.unpack(">f", base64.b64decode(v))[0]
            self.assertAlmostEqual(v, 1.20e-03)

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "prbs-type": "prbs31",
                },
            )

            self.set_logs = {}  # clear set_logs

            conn.delete(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/prbs-mode",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x3000000010000],
                {
                    "prbs-type": "none",
                },
            )

        await asyncio.to_thread(test)


class TestGearboxServer(TestBase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-gearbox")
        self.conn.delete_all("goldstone-interfaces")
        self.conn.apply()

        self.set_logs = {}

        self.patch_taish()

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        ifserver = InterfaceServer(self.conn, "", platform_info)
        self.server = GearboxServer(self.conn, ifserver)

    async def test_synce_reference_clocks(self):

        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())
        self.set_logs = {}

        def test():
            conn = Connector()
            conn.set("/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1")
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/synce-reference-clocks/synce-reference-clock[name='0']/config/name",
                "0",
            )
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/synce-reference-clocks/synce-reference-clock[name='0']/config/reference-interface",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs[0x1],
                {
                    "pgmrclk-assignment": "oid:0x3000000010000,oid:0x3000000010000",
                    "tributary-mapping": '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]',
                },
            )

        await asyncio.to_thread(test)

    async def test_gearbox_create_connection(self):
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            conn = Connector()
            conn.set("/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1")
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                True,
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/connections/connection[client-interface='Interface1/0/1'][line-interface='Interface1/1/1']/config/client-interface",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/connections/connection[client-interface='Interface1/0/1'][line-interface='Interface1/1/1']/config/line-interface",
                "Interface1/1/1",
            )
            conn.apply()

        await asyncio.to_thread(test)

    async def test_gearbox_enable_flexible_connection(self):
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            conn = Connector()
            conn.set("/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1")
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                True,
            )
            conn.apply()

            self.assertTrue(self.set_logs[0x1]["tributary-mapping"], [])
            self.set_logs = {}  # clear set_logs
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/enable-flexible-connection",
                False,
            )
            conn.apply()

            self.assertTrue(
                self.set_logs[0x1]["tributary-mapping"],
                '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]',
            )

        await asyncio.to_thread(test)

    async def test_invalid_creation(self):
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            conn = Connector()
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='10']/config/name", "10"
            )
            with self.assertRaises(CallbackFailedError):
                conn.apply()

        await asyncio.to_thread(test)

    async def test_oper_cb(self):
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test_oper_cb():
            conn = Connector()

            data = conn.get_operational("/goldstone-gearbox:gearboxes/gearbox")
            self.assertEqual(len(data), 1)
            data = list(data)[0]
            self.assertEqual(data["state"]["admin-status"], "UP")
            self.assertEqual(data["state"]["oper-status"], "UP")
            self.assertEqual(data["state"]["enable-flexible-connection"], False)
            connection = list(data["connections"]["connection"])
            self.assertEqual(len(connection), 1)
            self.assertEqual(connection[0]["client-interface"], "Interface1/0/1")
            self.assertEqual(connection[0]["line-interface"], "Interface1/1/1")

            clock = list(data["synce-reference-clocks"]["synce-reference-clock"])
            self.assertEqual(len(clock), 2)
            self.assertEqual(clock[0]["state"]["reference-interface"], "Interface1/0/1")
            self.assertEqual(
                clock[0]["state"]["component-connection"],
                {"input-reference": "0", "dpll": "1"},
            )
            self.assertEqual(clock[1]["state"]["reference-interface"], "Interface1/1/1")
            self.assertEqual(
                clock[1]["state"]["component-connection"],
                {"input-reference": "1", "dpll": "1"},
            )

        await asyncio.to_thread(test_oper_cb)

    async def test_reconcile(self):
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())
        self.assertEqual(
            self.set_logs[0x1],
            {
                "tributary-mapping": '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]',
                "admin-status": "up",
            },
        )

        self.assertEqual(
            self.set_logs[0x3000000010000],
            {
                "provision-mode": "none",
                "signal-rate": "100-gbe",
                "pin-mode": "pam4",
                "fec-type": "rs",
                "mtu": DEFAULT_MTU,
                "mru": DEFAULT_MTU,
                "macsec-static-key": "",
            },
        )

        self.assertEqual(
            self.set_logs[0x2000000010000],
            {
                "provision-mode": "none",
                "signal-rate": "100-gbe",
                "pin-mode": "nrz",
                "fec-type": "rs",
                "mtu": DEFAULT_MTU,
                "mru": DEFAULT_MTU,
                "auto-negotiation": "false",
            },
        )

    async def test_reconcile_with_admin_status_down(self):
        def setup():
            conn = Connector()
            conn.set("/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1")
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/admin-status",
                "DOWN",
            )
            conn.apply()

        await asyncio.to_thread(setup)

        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        self.assertEqual(
            self.set_logs[0x1],
            {
                "tributary-mapping": '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]',
                "admin-status": "down",
            },
        )

    async def test_reconcile_with_admin_status_up(self):
        def setup():
            conn = Connector()
            conn.set("/goldstone-gearbox:gearboxes/gearbox[name='1']/config/name", "1")
            conn.set(
                "/goldstone-gearbox:gearboxes/gearbox[name='1']/config/admin-status",
                "UP",
            )
            conn.apply()

        await asyncio.to_thread(setup)

        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        self.assertEqual(
            self.set_logs[0x1],
            {
                "tributary-mapping": '[{"oid:0x3000000010000": ["oid:0x2000000010000"]}]',
                "admin-status": "up",
            },
        )

        self.assertEqual(
            self.set_logs[0x2000000010000],
            {
                "provision-mode": "none",
                "signal-rate": "100-gbe",
                "pin-mode": "nrz",
                "fec-type": "rs",
                "mtu": DEFAULT_MTU,
                "mru": DEFAULT_MTU,
                "auto-negotiation": "false",
            },
        )

        self.assertEqual(
            self.set_logs[0x3000000010000],
            {
                "provision-mode": "none",
                "signal-rate": "100-gbe",
                "pin-mode": "pam4",
                "fec-type": "rs",
                "mtu": DEFAULT_MTU,
                "mru": DEFAULT_MTU,
                "macsec-static-key": "",
            },
        )

    async def test_reconcile_with_intf_admin_status_up(self):
        def setup():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name",
                "Interface1/0/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status",
                "UP",
            )
            conn.apply()

        await asyncio.to_thread(setup)

        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        self.assertEqual(
            self.set_logs[0x2000000010000],
            {
                "auto-negotiation": "false",
                "fec-type": "rs",
                "mru": DEFAULT_MTU,
                "mtu": DEFAULT_MTU,
                "pin-mode": "nrz",
                "provision-mode": "normal",
                "signal-rate": "100-gbe",
            },
        )

    async def test_reconcile_with_intf_pin_mode(self):
        def setup():
            conn = Connector()
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/name",
                "Interface1/1/1",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/pin-mode",
                "NRZ",
            )
            conn.set(
                "/goldstone-interfaces:interfaces/interface[name='Interface1/1/1']/config/admin-status",
                "UP",
            )

            conn.apply()

        await asyncio.to_thread(setup)

        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

        self.assertEqual(
            self.set_logs[0x3000000010000],
            {
                "fec-type": "rs",
                "macsec-static-key": "",
                "mru": DEFAULT_MTU,
                "mtu": DEFAULT_MTU,
                "pin-mode": "nrz",
                "provision-mode": "normal",
                "signal-rate": "100-gbe",
            },
        )
