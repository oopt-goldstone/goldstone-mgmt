import unittest
import logging
import os
import sys
import itertools

logger = logging.getLogger(__name__)

libpath = os.path.join(os.path.dirname(__file__), "../../../lib")
sys.path.insert(0, libpath)

from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.connector import Error

from goldstone.north.cli.root import Root
from goldstone.north.cli import transponder

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

EXPECTED_RUN_CONF = """transponder piu1
  admin-status up
  netif 0
    tx-dis true
    quit
  quit
!"""


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
        if isinstance(oper_data, Exception):
            raise oper_data
        logger.info(
            f"{xpath=}, {default=}, {include_implicit_defaults=}, {strip=}, {one=}, {ds=}"
        )
        return oper_data.get(xpath, default)


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
