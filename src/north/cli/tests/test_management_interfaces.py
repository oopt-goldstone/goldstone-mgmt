import unittest
import logging
import os
import sys
import itertools

logger = logging.getLogger(__name__)

libpath = os.path.join(os.path.dirname(__file__), "../../../lib")
sys.path.insert(0, libpath)

from goldstone.north.cli.base import InvalidInput
from goldstone.north.cli.root import Root
from goldstone.north.cli import management_interface

from .test_util import MockConnector

INTF_OPER_DATA = [
    {
        "name": "lo",
        "state": {"oper-status": "UP", "admin-status": "UP"},
        "ipv4": {
            "addresses": {
                "address": [
                    {
                        "ip": "127.0.0.1",
                        "config": {"ip": "127.0.0.1"},
                        "state": {"ip": "127.0.0.1", "prefix-length": 8},
                    }
                ]
            }
        },
    },
    {
        "name": "eth0",
        "state": {"oper-status": "UP", "admin-status": "UP"},
        "ipv4": {
            "addresses": {
                "address": [
                    {
                        "ip": "192.168.0.1",
                        "config": {"ip": "192.168.0.1"},
                        "state": {"ip": "192.168.0.1", "prefix-length": 24},
                    }
                ]
            },
            "neighbors": {
                "neighbor": [
                    {
                        "ip": "192.168.0.2",
                        "state": {"link-layer-address": "12:34:56:78:90:12"},
                    },
                    {
                        "ip": "192.168.0.3",
                    },
                ]
            },
        },
    },
]

EXPECTED_SHOW = """------------  --
admin-status  up
oper-status   up
------------  --

IPv4 address
--------------
192.168.0.1/24
--------------

IPv4 neighbor
-----------  -----------------
192.168.0.2  12:34:56:78:90:12
192.168.0.3  incomplete
-----------  -----------------"""


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        conn = MockConnector()
        root = Root(conn)
        root.exec("clear datastore all", no_fail=False)

    async def test_aaa(self):
        conn = MockConnector()
        root = Root(conn)
        data = ["eth0"]
        conn.oper_data = {
            "/goldstone-mgmt-interfaces:interfaces/interface": INTF_OPER_DATA,
            "/goldstone-mgmt-interfaces:interfaces/interface/name": data,
            "/goldstone-mgmt-interfaces:interfaces/interface[name='eth0']": INTF_OPER_DATA[
                1
            ],
        }
        ifctx = root.exec("management-interface eth0", no_fail=False)

        logger = logging.getLogger("stdout")
        with self.assertLogs(logger=logger) as l:
            ifctx.exec("show", no_fail=False)
            show = "\n".join(
                itertools.chain.from_iterable(r.msg.split("\n") for r in l.records)
            )
            self.assertEqual(show, EXPECTED_SHOW)

        ifctx.exec("shutdown", no_fail=False)
        v = conn.get(
            "/goldstone-mgmt-interfaces:interfaces/interface/config/admin-status",
            one=True,
        )
        self.assertEqual(v, "DOWN")
