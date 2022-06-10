import unittest
from unittest import mock
from goldstone.south.tai.transponder import TransponderServer
import asyncio
import logging
import json
import time
import itertools
import libyang
from goldstone.lib.core import ServerBase
from goldstone.lib.connector.sysrepo import Connector
import os
import json
from taish import TAIException

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
                    "piu": {"state": {"status": ["PRESENT"]}},
                }
            )

        return {"goldstone-platform:components": {"component": components}}

    async def start(self):
        return await super().start()


class TestTransponderServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()

        taish = mock.AsyncMock()
        taish.list.return_value = {"1": None}

        def noop():
            pass

        taish.close = noop
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
                ret = "2"
            else:
                raise TAIException(0, "mock")

            if kwargs.get("with_metadata"):
                return ret, mock.MagicMock()
            return ret

        module.monitor = monitor
        module.get = get

        obj = mock.AsyncMock()
        obj.monitor = monitor
        obj.get = get

        def f(*args):
            return obj

        module.get_netif = f
        module.get_hostif = f

        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        self.patchers = [
            mock.patch("taish.AsyncClient", return_value=taish),
        ]

        [p.start() for p in self.patchers]

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

            self.assertEqual(len(server.event_obj), 1)

        tasks.append(asyncio.create_task(asyncio.to_thread(test2)))

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        alive = False

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await server.stop()

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

    async def asyncTearDown(self):
        self.alive = False
        [p.stop() for p in self.patchers]
        self.conn.stop()


if __name__ == "__main__":
    unittest.main()
