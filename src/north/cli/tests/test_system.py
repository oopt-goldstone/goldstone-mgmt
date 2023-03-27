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
from goldstone.north.cli import system

from .test_util import MockConnector


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        conn = MockConnector()
        root = Root(conn)
        root.exec("clear datastore all", no_fail=False)

    async def test_aaa(self):
        conn = MockConnector()
        root = Root(conn)
        logger = logging.getLogger("stdout")
        system_ctx = root.exec("system", no_fail=False)

        system_ctx.exec("aaa authentication login default local", no_fail=False)

        v = conn.get(
            "/goldstone-aaa:aaa/authentication/config/authentication-method", one=True
        )
        self.assertEqual(v, "local")

        system_ctx.exec("no aaa authentication login", no_fail=False)

        v = conn.get("/goldstone-aaa:aaa/authentication/config/authentication-method")
        self.assertEqual(v, None)

        system_ctx.exec("aaa authentication login default group tacacs", no_fail=False)

        v = conn.get(
            "/goldstone-aaa:aaa/authentication/config/authentication-method", one=True
        )
        self.assertEqual(v, "tacacs")

        system_ctx.exec("no aaa authentication login", no_fail=False)

        v = conn.get("/goldstone-aaa:aaa/authentication/config/authentication-method")
        self.assertEqual(v, None)

    async def test_tacacs(self):
        conn = MockConnector()
        root = Root(conn)
        logger = logging.getLogger("stdout")
        system_ctx = root.exec("system", no_fail=False)

        system_ctx.exec("tacacs host 10.10.10.1 key hello", no_fail=False)

        v = conn.get("/goldstone-aaa:aaa/server-groups/server-group", one=True)
        self.assertEqual(
            v,
            {
                "name": "TACACS+",
                "config": {"name": "TACACS+"},
                "servers": {
                    "server": [
                        {
                            "address": "10.10.10.1",
                            "config": {"address": "10.10.10.1", "timeout": 300},
                            "tacacs": {"config": {"port": 49, "secret-key": "hello"}},
                        }
                    ]
                },
            },
        )

        system_ctx.exec("no tacacs host 10.10.10.1", no_fail=False)
        v = conn.get("/goldstone-aaa:aaa/server-groups/server-group", one=True)
        self.assertEqual(v, {"name": "TACACS+", "config": {"name": "TACACS+"}})
