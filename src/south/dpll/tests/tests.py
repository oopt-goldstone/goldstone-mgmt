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

        async def set_(*args):
            self.set_logs.append(args)

        async def set_multiple(*args):
            for a in args[0]:
                self.set_logs.append(a)

        async def get(*args, **kwargs):
            if args[0] in ["dpll-mode"]:
                return "freerun"
            elif args[0] in ["dpll-state"]:
                return "freerun"
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
                                    "config": {"name": "1"},
                                    "state": {"mode": "freerun", "state": "freerun"},
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
