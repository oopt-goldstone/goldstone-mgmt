import unittest
import logging
import os
import sys
import itertools

logger = logging.getLogger(__name__)

libpath = os.path.join(os.path.dirname(__file__), "../../../lib")
sys.path.insert(0, libpath)

from goldstone.north.cli.root import Root

from .test_util import MockConnector

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


class Test(unittest.IsolatedAsyncioTestCase):
    async def test_save(self):
        conn = MockConnector()
        root = Root(conn)
        ifname = "Interface0"
        data = [ifname]
        conn.oper_data = {
            "/goldstone-interfaces:interfaces/interface": INTF_OPER_DATA,
            "/goldstone-interfaces:interfaces/interface/name": data,
        }

        logger = logging.getLogger("stdout")

        root.exec("clear datastore all", no_fail=False)
        root.exec("save all", no_fail=False)

        v = conn.get_startup("/goldstone-interfaces:interfaces")
        self.assertEqual(v, None)
        v = conn.get("/goldstone-interfaces:interfaces")
        self.assertEqual(v, None)

        ifctx = root.exec(f"interface {ifname}", no_fail=False)
        ifctx.exec("admin-status up", no_fail=False)

        root.exec("save goldstone-interfaces", no_fail=False)

        v = conn.get_startup("/goldstone-interfaces:interfaces")
        self.assertEqual(
            v,
            {
                "interface": [
                    {
                        "name": "Interface0",
                        "config": {"name": "Interface0", "admin-status": "UP"},
                    }
                ]
            },
        )

        root.exec("clear datastore all startup", no_fail=False)
        v = conn.get_startup("/goldstone-interfaces:interfaces")
        self.assertEqual(v, None)
        v = conn.get("/goldstone-interfaces:interfaces")
        self.assertNotEqual(v, None)
