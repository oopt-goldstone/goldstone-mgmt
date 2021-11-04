import unittest
from unittest import mock
from goldstone.south.tai.transponder import TransponderServer
import sysrepo
import asyncio
import logging
import json
import time
import itertools

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)


class TestTransponderServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-transponder")
            sess.apply_changes()

    async def test_tai_hotplug(self):
        ataish = mock.AsyncMock()
        ataish.list.return_value = {"/dev/piu1": None}

        def noop():
            pass

        ataish.close = noop
        module = ataish.get_module.return_value

        async def monitor(*args, **kwargs):
            while True:
                print("monitoring..")
                await asyncio.sleep(1)

        async def get(*args, **kwargs):
            if args[0] in ["alarm-notification", "notify"]:
                return "(nil)"
            else:
                return mock.MagicMock()

        module.monitor = monitor
        module.get = get

        obj = mock.AsyncMock()
        obj.monitor = monitor
        obj.get = get

        def f(*args):
            return obj

        module.get_netif = f
        module.get_hostif = f

        taish = mock.MagicMock()
        taish.list.return_value = {"/dev/piu1": None}
        module = taish.get_module.return_value
        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        with (
            mock.patch("taish.AsyncClient", return_value=ataish),
            mock.patch("taish.Client", return_value=taish),
        ):
            self.server = TransponderServer(self.conn, "127.0.0.1:50051")

            servers = [self.server]

            tasks = list(
                asyncio.create_task(c)
                for c in itertools.chain.from_iterable(
                    [await s.start() for s in servers]
                )
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

                    print(sess.get_data("/goldstone-transponder:modules/module/name"))

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

    async def asyncTearDown(self):
        self.conn.disconnect()


if __name__ == "__main__":
    unittest.main()
