import unittest
from unittest import mock
from goldstone.south.tai.transponder import TransponderServer
import sysrepo
import asyncio
import logging
import json
import time
import itertools
import libyang
from goldstone.lib.core import ServerBase
import os
import json
from taish import TAIException

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)

logger = logging.getLogger(__name__)


class MockPlatformServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-platform")

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
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
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-transponder")
            sess.apply_changes()

        taish = mock.AsyncMock()
        taish.list.return_value = {"/dev/piu1": None}

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

        self.alive = True

        def p_server():
            conn = sysrepo.SysrepoConnection()
            pserver = MockPlatformServer(conn)

            async def f():
                await pserver.start()
                while self.alive:
                    await asyncio.sleep(1)

            asyncio.run(f())
            conn.close()

        asyncio.create_task(asyncio.to_thread(p_server))

        for _ in range(10):
            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                try:
                    logger.debug(
                        sess.get_data("/goldstone-platform:components/component")
                    )
                except sysrepo.SysrepoError as e:
                    logger.error(e)
                else:
                    break
                await asyncio.sleep(1)

        self.server = TransponderServer(self.conn, "", [])
        tasks = list(asyncio.create_task(c) for c in await self.server.start())

        def test():
            for _ in range(10):
                with self.conn.start_session() as sess:
                    sess.switch_datastore("operational")
                    v = sess.get_data("/goldstone-transponder:modules/module/name")
                    logger.info(v)
                    if list(v["modules"]["module"])[0]["name"] == "piu1":
                        break
            else:
                self.assertTrue(False, f"piu1 didn't show up in oper ds")

        await asyncio.to_thread(test)

        async def test2():
            # one PIU must be initialized in the server
            self.assertEqual(len(self.server.event_obj), 1)

        tasks.append(asyncio.create_task(test2()))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        await self.server.stop()

        self.alive = False

    async def test_tai_hotplug(self):
        self.server = TransponderServer(self.conn, "", [])

        servers = [self.server]

        tasks = list(
            asyncio.create_task(c)
            for c in itertools.chain.from_iterable([await s.start() for s in servers])
        )

        def test():

            with self.conn.start_session() as sess:
                name = "piu1"
                sess.set_item(
                    f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                    name,
                )
                sess.set_item(
                    f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
                    "up",
                )
                sess.apply_changes()

            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")

                ly_ctx = sess.get_ly_ctx()
                name = "goldstone-platform:piu-notify-event"
                notification = {
                    "name": "piu1",
                    "status": ["PRESENT"],
                    "cfp2-presence": "PRESENT",
                }

                n = json.dumps({name: notification})
                dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
                sess.notification_send_ly(dnode)

                time.sleep(2)

                logger.info(sess.get_data("/goldstone-transponder:modules/module/name"))

                notification = {
                    "name": "piu1",
                }
                n = json.dumps({name: notification})
                dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
                sess.notification_send_ly(dnode)

                time.sleep(2)

        tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        await self.server.stop()

    async def test_component_connection(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        server = TransponderServer(self.conn, "", platform_info)

        tasks = list(asyncio.create_task(c) for c in await server.start())

        def test():

            with self.conn.start_session() as sess:
                sess.switch_datastore("operational")
                name = "piu1"
                data = sess.get_data("/goldstone-transponder:modules/module")
                data = libyang.xpath_get(data, "modules/module/component-connection/platform/component")
                self.assertEqual(data, ["piu1"])

        tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        await server.stop()

    async def asyncTearDown(self):
        self.alive = False
        [p.stop() for p in self.patchers]
        self.conn.disconnect()


if __name__ == "__main__":
    unittest.main()
