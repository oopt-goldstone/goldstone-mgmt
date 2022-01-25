import unittest
import logging
import os
import sys

logger = logging.getLogger(__name__)

libpath = os.path.join(os.path.dirname(__file__), "../../../lib")
sys.path.insert(0, libpath)

from goldstone.lib.connector.sysrepo import Connector

from goldstone.north.cli.base import InvalidInput
from goldstone.north.cli.root import Root
from goldstone.north.cli import interface

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

INTF_OPER_DATA = [
    {
        "name": "Interface0",
        "state": {"oper-status": "UP", "admin-status": "UP"},
    },
    {
        "name": "Interface1",
        "state": {"oper-status": "DOWN", "admin-status": "UP"},
    },
    {
        "name": "Interface2",
        "state": {"oper-status": "DOWN"},
    },
    {
        "name": "Interface3",
        "state": {"admin-status": "UP"},
    },
]


def ifxpath(ifname):
    return f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"


class MockConnector(Connector):
    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        if ds != "operational":
            return super().get(
                xpath, default, include_implicit_defaults, strip, one, ds
            )

        oper_data = getattr(self, "oper_data", {})
        logger.info(
            f"{xpath=}, {default=}, {include_implicit_defaults=}, {strip=}, {one=}, {ds=}"
        )
        return oper_data.get(xpath, default)


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = MockConnector()
        self.conn.delete_all("goldstone-interfaces")
        self.conn.apply()

    async def test_show_interface_brief(self):

        conn = MockConnector()
        root = Root(conn)
        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface": INTF_OPER_DATA,
        }
        logger = logging.getLogger("stdout")

        with self.assertLogs(logger=logger) as l:
            root.exec("show interface brief", no_fail=False)
            lines = l.records[0].msg.split("\n")
            for i, line in enumerate(lines[3:-1]):
                elems = [e.strip() for e in line.split("|") if e]
                self.assertEqual(elems[0], INTF_OPER_DATA[i]["name"])
                self.assertEqual(
                    elems[1], INTF_OPER_DATA[i]["state"].get("oper-status", "-").lower()
                )
                self.assertEqual(
                    elems[2],
                    INTF_OPER_DATA[i]["state"].get("admin-status", "-").lower(),
                )

    async def test_auto_nego_help(self):
        conn = MockConnector()
        root = Root(conn)
        data = ["Interface0"]
        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface/name": data,
        }
        logger = logging.getLogger("stderr")

        ifctx = root.exec("interface Interface0", no_fail=False)

        with self.assertRaises(InvalidInput) as cm:
            ifctx.exec("auto-nego", no_fail=False)

        self.assertEqual(
            str(cm.exception), "usage: auto-negotiate [enable|disable|advertise]"
        )

    async def test_show_in_interface_ctx(self):
        conn = MockConnector()
        root = Root(conn)
        data = ["Interface0"]
        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface": INTF_OPER_DATA,
            "/goldstone-interfaces:interfaces/interface/name": data,
        }
        logger = logging.getLogger("stdout")

        with self.assertLogs(logger=logger) as l:
            root.exec("show interface brief", no_fail=False)
            ifctx = root.exec("interface Interface0", no_fail=False)
            ifctx.exec("show interface brief", no_fail=False)

            # global show and show in the interface ctx must have the same output
            self.assertEqual(l.records[0].msg, l.records[1].msg)

    async def test_clear_datastore_all(self):
        conn = MockConnector()
        root = Root(conn)
        ifname = "Interface0"
        data = [ifname]
        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface": INTF_OPER_DATA,
            "/goldstone-interfaces:interfaces/interface/name": data,
        }

        xpath = ifxpath(ifname) + "/config/admin-status"

        ifctx = root.exec("interface Interface0", no_fail=False)
        ifctx.exec("admin-status up", no_fail=False)

        admin_status = conn.get(xpath)
        self.assertEqual(admin_status, "UP")

        root.exec("clear datastore all", no_fail=False)
        admin_status = conn.get(xpath)
        self.assertEqual(admin_status, None)
