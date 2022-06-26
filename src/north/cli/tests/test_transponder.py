import unittest
import logging
import os
import sys
import itertools

logger = logging.getLogger(__name__)

libpath = os.path.join(os.path.dirname(__file__), "../../../lib")
sys.path.insert(0, libpath)

from goldstone.lib.errors import Error

from goldstone.north.cli.root import Root
from goldstone.north.cli import transponder

from .test_util import MockConnector

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

EXPECTED_RUN_CONF = """transponder piu1
  admin-status up
  netif 0
    tx-dis true
    quit
  quit"""

EXPECTED_RUN_CONF2 = """transponder piu1
  hostif 0
    fec-type rs
    quit
!
  hostif 1
    fec-type rs
    quit
!
  hostif 2
    fec-type rs
    quit
!
  hostif 3
    fec-type rs
    quit
  quit"""

EXPECTED_RUN_CONF3 = """transponder piu1
  hostif 0
    fec-type rs
    quit
!
  hostif 1
    fec-type rs
    quit
!
  hostif 2
    fec-type rs
    quit
  quit"""


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = MockConnector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()

    async def test_show_transponder_details(self):

        root = Root(self.conn)
        self.conn.oper_data = {
            "/goldstone-transponder:modules/module/name": ["piu1"],
        }

        ctx = root.exec("transponder piu1", no_fail=False)

        self.conn.oper_data = Error("test")

        with self.assertRaises(Error):
            ctx.exec("show details", no_fail=False)

    async def test_show_run(self):
        root = Root(self.conn)
        self.conn.oper_data = {
            "/goldstone-transponder:modules/module/name": ["piu1"],
            "/goldstone-transponder:modules/module[name='piu1']/network-interface/name": [
                "0"
            ],
        }

        ctx = root.exec("transponder piu1", no_fail=False)
        ctx.exec("admin-status up", no_fail=False)

        netif = ctx.exec("netif 0", no_fail=False)
        netif.exec("tx-dis true", no_fail=False)

        logger = logging.getLogger("stdout")

        with self.assertLogs(logger=logger) as l:
            root.exec("show running-config transponder", no_fail=False)
            run_conf = "\n".join(
                itertools.chain.from_iterable(r.msg.split("\n") for r in l.records)
            )

        self.assertEqual(run_conf, EXPECTED_RUN_CONF)

    async def test_hostif(self):
        root = Root(self.conn)
        self.conn.oper_data = {
            "/goldstone-transponder:modules/module/name": ["piu1"],
            "/goldstone-transponder:modules/module[name='piu1']/host-interface/name": [
                "0",
                "1",
                "2",
                "3",
            ],
        }

        ctx = root.exec("transponder piu1", no_fail=False)

        hostif = ctx.exec(f"hostif .", no_fail=False)  # select all host interfaces
        hostif.exec("fec-type rs", no_fail=False)

        logger = logging.getLogger("stdout")

        with self.assertLogs(logger=logger) as l:
            root.exec("show running-config transponder", no_fail=False)
            run_conf = "\n".join(
                itertools.chain.from_iterable(r.msg.split("\n") for r in l.records)
            )

        self.assertEqual(run_conf, EXPECTED_RUN_CONF2)

        ctx.exec(f"no hostif 3", no_fail=False)

        with self.assertLogs(logger=logger) as l:
            root.exec("show running-config transponder", no_fail=False)
            run_conf = "\n".join(
                itertools.chain.from_iterable(r.msg.split("\n") for r in l.records)
            )

        self.assertEqual(run_conf, EXPECTED_RUN_CONF3)
