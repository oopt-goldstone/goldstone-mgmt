import unittest
from unittest import mock
from goldstone.south.dpll.dpll import DPLLServer
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

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)


class TestDPLLServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-dpll")
            sess.apply_changes()

        taish = mock.AsyncMock()

        self.set_logs = []

        self.attrs = {
            "input-reference-priority": "0,1,2,3,4,5,6,7",
            "dpll-mode": "freerun",
            "dpll-state": "freerun",
            "selected-reference": "5",
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

    async def test_basic(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = DPLLServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                v = sess.get_data("/goldstone-dpll:dplls/dpll/name")
                v = libyang.xpath_get(v, "dplls/dpll/name")
                self.assertEqual(v, ["1"])

                v = sess.get_data("/goldstone-dpll:dplls/dpll")
                self.assertEqual(
                    v,
                    {
                        "dplls": {
                            "dpll": [
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
                                        "state": "freerun",
                                        "selected-reference": "4",
                                    },
                                }
                            ]
                        }
                    },
                )

        tasks.append(asyncio.to_thread(test))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.server.stop()

    async def test_mode(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = DPLLServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                dpll = "1"
                sess.set_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/name", dpll
                )
                sess.set_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/mode",
                    "automatic",
                )

                sess.apply_changes()

        tasks.append(asyncio.to_thread(test))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.server.stop()

    async def test_priority(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = DPLLServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            with self.conn.start_session() as sess:
                sess.switch_datastore("running")
                dpll = "1"
                ref = "0"
                sess.set_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/config/name", dpll
                )
                sess.set_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/name",
                    ref,
                )
                sess.set_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/priority",
                    10,
                )
                sess.apply_changes()

                sess.delete_item(
                    f"/goldstone-dpll:dplls/dpll[name='{dpll}']/input-references/input-reference[name='{ref}']/config/priority",
                )
                sess.apply_changes()

                self.assertEqual(
                    self.set_logs,
                    [
                        ("input-reference-priority", "10,1,2,3,4,5,6,7"),
                        ("input-reference-priority", "0,1,2,3,4,5,6,7"),
                    ],
                )

        tasks.append(asyncio.to_thread(test))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.server.stop()
