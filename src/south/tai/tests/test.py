import unittest
from unittest import mock
import asyncio
import logging
import json
import time
import libyang
import os
from taish import TAIException

from goldstone.lib.core import ServerBase
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import *

from goldstone.south.tai.transponder import TransponderServer

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)


class MockPlatformServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-platform")

    async def oper_cb(self, xpath, priv):
        components = []
        for i in range(4):
            name = f"piu{i+1}"
            components.append(
                {
                    "name": name,
                    "config": {"name": name},
                    "state": {"type": "PIU"},
                    "piu": {
                        "state": {"status": ["PRESENT"], "cfp2-presence": "PRESENT"}
                    },
                }
            )

        return {"goldstone-platform:components": {"component": components}}

    async def start(self):
        return await super().start()


class TestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()

        taish = mock.AsyncMock()
        taish.list.return_value = {"1": None}

        self.objects = {}

        async def remove(*args, **kwargs):
            oid = args[0]
            if oid == "module(1)":
                return
            if oid not in self.objects:
                raise TAIException(-1, f"{oid} not found")
            self.objects.pop(oid)

        taish.remove = remove

        module = taish.get_module.return_value

        async def monitor(*args, **kwargs):
            while True:
                logger.debug("monitoring..")
                await asyncio.sleep(1)

        async def get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                ret = "(nil)"
            elif args[0] == "admin-status":
                ret = '"up"'
            elif args[0] == "num-network-interfaces":
                ret = "1"
            elif args[0] == "num-host-interfaces":
                ret = "4"
            elif args[0] == "line-rate":
                ret = "400g"
            else:
                raise TAIException(0, "mock")

            if kwargs.get("with_metadata"):
                return ret, mock.MagicMock()
            return ret

        async def get_attribute_metadata(*args, **kwargs):
            if args[0] == "losi":
                raise TAIException(-1, "fail")
            return mock.MagicMock()

        module.monitor = monitor
        module.get = get

        async def get_attribute_capability(*args, **kwargs):
            m = mock.MagicMock()
            m.min = ""
            m.max = ""
            return m

        def create_obj(oid):
            obj = mock.AsyncMock()
            obj.monitor = monitor
            obj.get = get
            obj.get_attribute_metadata = get_attribute_metadata
            obj.get_attribute_capability = get_attribute_capability
            obj.oid = oid
            self.objects[oid] = obj
            return obj

        def get_netif(*args):
            index = args[0]
            oid = f"netif({index})"
            obj = self.objects.get(oid)
            if obj:
                return obj
            raise TAIException(-1, f"{oid} not found")

        def get_hostif(*args):
            index = args[0]
            oid = f"hostif({index})"
            obj = self.objects.get(oid)
            if obj:
                return obj
            raise TAIException(-1, f"{oid} not found")

        async def create_netif(*args, **kwargs):
            index = args[0]
            oid = f"netif({index})"
            obj = self.objects.get(oid)
            if obj:
                raise TAIException(-1, f"{oid} already exists")
            return create_obj(oid)

        async def create_hostif(*args, **kwargs):
            index = args[0]
            oid = f"hostif({index})"
            obj = self.objects.get(oid)
            if obj:
                raise TAIException(-1, f"{oid} already exists")
            return create_obj(oid)

        module.get_netif = get_netif
        module.get_hostif = get_hostif
        module.create_netif = create_netif
        module.create_hostif = create_hostif
        module.get_attribute_capability = get_attribute_capability
        module.location = "1"
        module.oid = "module(1)"

        self.patchers = [
            mock.patch("taish.AsyncClient", return_value=taish),
        ]

        [p.start() for p in self.patchers]

    async def asyncTearDown(self):
        self.alive = False
        [p.stop() for p in self.patchers]
        self.conn.stop()


class TestTransponderServer(TestBase):
    async def test_tai_init(self):
        # this needs to run in another thread because TransponderServer queries
        # /goldstone-platform in the main event loop
        # * sysrepo-python doesn't support getting items asynchronously
        alive = True

        def p_server():
            conn = Connector()
            s = MockPlatformServer(conn)

            async def f():
                t = await s.start()
                while alive:
                    await asyncio.sleep(1)
                s.stop()
                await asyncio.gather(*t)

            asyncio.run(f())
            conn.close()

        tasks = [asyncio.create_task(asyncio.to_thread(p_server))]

        def test():
            conn = Connector()

            for _ in range(10):
                v = conn.get_operational("/goldstone-platform:components/component")
                if v:
                    break
                time.sleep(1)
            else:
                self.assertTrue(False, f"component doesn't show up in oper ds")

        await asyncio.to_thread(test)

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        server = TransponderServer(self.conn, "", platform_info)
        tasks += list(asyncio.create_task(c) for c in await server.start())

        def test2():
            conn = Connector()
            for _ in range(10):
                v = conn.get_operational(
                    "/goldstone-transponder:modules/module/name", one=True
                )
                if v == "piu1":
                    break
                time.sleep(1)
            else:
                self.assertTrue(False, f"piu1 didn't show up in oper ds")

            self.assertEqual(len(server.modules), 1)

        await asyncio.to_thread(test2)
        alive = False
        await server.stop()

        for t in tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def test_tai_hotplug(self):
        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        server = TransponderServer(self.conn, "", platform_info)
        tasks = list(asyncio.create_task(c) for c in await server.start())

        def test():
            conn = Connector()

            name = "piu1"
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
                "up",
            )
            conn.apply()

            name = "goldstone-platform:piu-notify-event"
            notification = {
                "name": "piu1",
                "status": ["PRESENT"],
                "cfp2-presence": "PRESENT",
            }
            conn.send_notification(name, notification)

            time.sleep(2)

            logger.info(
                conn.get_operational("/goldstone-transponder:modules/module/name")
            )

            notification = {
                "name": "piu1",
            }
            conn.send_notification(name, notification)
            time.sleep(2)

        tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await server.stop()

    async def test_component_connection(self):
        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        server = TransponderServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await server.start())

        def test():
            conn = Connector()
            name = "piu1"
            data = conn.get_operational("/goldstone-transponder:modules/module")
            data = libyang.xpath_get(data, "component-connection/platform/component")
            self.assertEqual(data, ["piu1"])

        tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await server.stop()


class TestTransponderServerAttributeHandling(TestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.server = TransponderServer(self.conn, "", platform_info)
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

    async def asyncTearDown(self):
        await self.server.stop()
        for t in self.tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        await super().asyncTearDown()

    def init(self, conn):
        name = "goldstone-platform:piu-notify-event"
        notification = {
            "name": "piu1",
            "status": ["PRESENT"],
            "cfp2-presence": "PRESENT",
        }
        conn.send_notification(name, notification)
        time.sleep(1)

    async def test_set_losi(self):
        def test():
            conn = Connector()
            self.init(conn)

            name = "piu1"
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/name",
                "0",
            )

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/losi",
                "true",
            )

            with self.assertRaisesRegex(
                CallbackFailedError, "unsupported attribute: losi"
            ):
                conn.apply()

        await asyncio.to_thread(test)

    async def test_set_line_rate(self):
        def test():
            conn = Connector()
            self.init(conn)

            v = list(sorted(self.objects.keys()))
            self.assertEqual(
                v, ["hostif(0)", "hostif(1)", "hostif(2)", "hostif(3)", "netif(0)"]
            )

            name = "piu1"
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                name,
            )
            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/name",
                "0",
            )

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/line-rate",
                "100g",
            )

            conn.apply()
            v = list(sorted(self.objects.keys()))
            self.assertEqual(v, ["hostif(0)", "netif(0)"])

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/line-rate",
                "200g",
            )

            conn.apply()
            v = list(sorted(self.objects.keys()))
            self.assertEqual(v, ["hostif(0)", "hostif(1)", "netif(0)"])

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/line-rate",
                "300g",
            )

            conn.apply()
            v = list(sorted(self.objects.keys()))
            self.assertEqual(v, ["hostif(0)", "hostif(1)", "hostif(2)", "netif(0)"])

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/line-rate",
                "400g",
            )

            conn.apply()
            v = list(sorted(self.objects.keys()))
            self.assertEqual(
                v, ["hostif(0)", "hostif(1)", "hostif(2)", "hostif(3)", "netif(0)"]
            )

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/host-interface[name='1']/config/name",
                "1",
            )

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/host-interface[name='1']/config/signal-rate",
                "100-gbe",
            )

            conn.set(
                f"/goldstone-transponder:modules/module[name='{name}']/network-interface[name='0']/config/line-rate",
                "100g",
            )
            with self.assertRaisesRegex(
                CallbackFailedError,
                "host-interface\(1\) has configuration that conflicts with line-rate: 100g",
            ):
                conn.apply()

        await asyncio.to_thread(test)


if __name__ == "__main__":
    unittest.main()
