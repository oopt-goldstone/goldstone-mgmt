import unittest
from unittest import mock
import libyang
import asyncio
import logging
import os
import json

from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector import create_server_connector
from goldstone.lib.errors import *
from goldstone.lib.util import call


from goldstone.south.dpll.dpll import DPLLServer

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)


class TestBase(unittest.IsolatedAsyncioTestCase):
    def patch_taish(self):
        taish = mock.AsyncMock()

        self.attrs = {
            "input-reference-priority": "0,1,2,3,4,5,6,7",
            "dpll-mode": "freerun",
            "dpll-state": "freerun",
            "selected-reference": "5",
            "phase-slope-limit": "7500",
            "loop-bandwidth": "1.0",
        }

        async def set_(*args):
            self.set_logs.append(args[0])
            self.attrs[args[0][0]] = args[0][1]

        async def set_multiple(*args, **kwargs):
            return [await set_(arg, **kwargs) for arg in args[0]]

        async def get(*args, **kwargs):
            if args[0] in self.attrs:
                return self.attrs[args[0]]
            elif args[0].startswith("ref-alarm-"):
                return "scm|gst"

            return mock.MagicMock()

        async def get_multiple(*args, **kwargs):
            return [await get(name, **kwargs) for name in args[0]]

        async def get_attribute_capability(*args, **kwargs):
            return mock.MagicMock()

        async def get_attribute_metadata(*args, **kwargs):
            return mock.MagicMock()

        module = taish.get_module.return_value
        module.get = get
        module.get_multiple = get_multiple
        module.set = set_
        module.set_multiple = set_multiple
        module.oid = 1
        module.obj.location = "1"
        module.location = "1"

        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        taish.list.return_value = {"1": module}

        self.patchers = [
            mock.patch("taish.AsyncClient", return_value=taish),
        ]

        [p.start() for p in self.patchers]


class TestDPLLServer(TestBase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-dpll")
        self.conn.apply()

        self.set_logs = []

        self.patch_taish()

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = DPLLServer(self.conn, "", platform_info)
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

    async def test_basic(self):
        def test():
            conn = Connector()
            v = conn.get_operational("/goldstone-dpll:dplls/dpll/name")
            self.assertEqual(v, ["1"])

            v = conn.get_operational("/goldstone-dpll:dplls/dpll", one=True)

            self.assertEqual(
                v,
                {
                    "name": "1",
                    "input-references": {
                        "input-reference": [
                            {
                                "name": "0",
                                "config": {"name": "0"},
                                "state": {
                                    "priority": 0,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "1",
                                "config": {"name": "1"},
                                "state": {
                                    "priority": 1,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "2",
                                "config": {"name": "2"},
                                "state": {
                                    "priority": 2,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "3",
                                "config": {"name": "3"},
                                "state": {
                                    "priority": 3,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "4",
                                "config": {"name": "4"},
                                "state": {
                                    "priority": 4,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "5",
                                "config": {"name": "5"},
                                "state": {
                                    "priority": 5,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "6",
                                "config": {"name": "6"},
                                "state": {
                                    "priority": 6,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                            {
                                "name": "7",
                                "config": {"name": "7"},
                                "state": {
                                    "priority": 7,
                                    "alarm": ["scm", "gst"],
                                },
                            },
                        ]
                    },
                    "config": {"name": "1"},
                    "state": {
                        "mode": "freerun",
                        "phase-slope-limit": 7500,
                        "loop-bandwidth": 1.0,
                        "state": "freerun",
                        "selected-reference": "5",
                    },
                },
            )

        await asyncio.create_task(asyncio.to_thread(test))

    async def test_mode(self):
        def test():
            conn = Connector()
            dpll = "1"
            conn.set(f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/name", dpll)
            conn.set(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/mode",
                "automatic",
            )
            conn.apply()

        await asyncio.to_thread(test)

    async def test_priority(self):
        def test():
            conn = Connector()
            dpll = "1"
            ref = "0"
            conn.set(f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/name", dpll)
            conn.set(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/name",
                ref,
            )
            conn.set(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/priority",
                10,
            )
            conn.apply()

            conn.delete(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/priority",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs,
                [
                    ("input-reference-priority", "10,1,2,3,4,5,6,7"),
                    ("input-reference-priority", "0,1,2,3,4,5,6,7"),
                ],
            )

        await asyncio.to_thread(test)

    async def test_phase_slope_limit(self):
        def test():
            conn = Connector()
            dpll = "1"
            conn.set(f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/name", dpll)
            conn.set(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/phase-slope-limit",
                7000,
            )

            conn.apply()

            self.assertEqual(
                self.set_logs,
                [
                    ("phase-slope-limit", "7000"),
                ],
            )

            self.set_logs = []

            conn.set(
                f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/phase-slope-limit",
                "unlimitted",
            )
            conn.apply()

            self.assertEqual(
                self.set_logs,
                [
                    ("phase-slope-limit", "0"),
                ],
            )

        await asyncio.to_thread(test)

    async def asyncTearDown(self):
        [p.stop() for p in self.patchers]
        await call(self.server.stop)
        [t.cancel() for t in self.tasks]
        self.conn.stop()
