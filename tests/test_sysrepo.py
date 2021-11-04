import unittest
from unittest import mock
import sysrepo
from goldstone.south.sonic.interfaces import InterfaceServer
from goldstone.south.tai.transponder import TransponderServer
import itertools
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
import functools
import time
import json

fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)


class MockK8S(object):
    def update_usonic_config(self, interface_map):
        return False

    async def run_bcmcmd_port(self, ifname, cmd):
        pass

    def get_default_iftype(self, ifname):
        return "KR4"

    async def bcm_ports_info(self, ports):
        return {}


class MockSONiC(object):
    def __init__(self):
        self.is_rebooting = False
        self.counter_if_dict = {}
        self.notif_if = {}
        self.k8s = MockK8S()
        self.logs = []

    def enable_counters(self):
        pass

    def cache_counters(self):
        pass

    def get_ifnames(self):
        return ["Ethernet1_1", "Ethernet2_1"]

    def set_config_db(self, ifname, key, value):
        self.logs.append((ifname, key, value))

    def get_counters(self, ifname):
        return {}

    def get_oper_status(self, ifname):
        return "up"

    def hgetall(self, db, key):
        return {}


async def to_subprocess(func):
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=1)
    return await loop.run_in_executor(executor, func)


def update_if():
    conn = sysrepo.SysrepoConnection()
    for _ in range(100):
        with conn.start_session() as sess:
            sess.switch_datastore("running")

            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

        with conn.start_session() as sess:
            sess.switch_datastore("running")
            name = "Ethernet1_1"
            sess.set_item(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            sess.set_item(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                "UP",
            )
            sess.apply_changes()


def update_xp():
    conn = sysrepo.SysrepoConnection()
    for _ in range(100):
        with conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-transponder")
            sess.apply_changes()

        with conn.start_session() as sess:
            name = "/dev/piu1"
            sess.set_item(
                f"/goldstone-transponder:modules/module[name='{name}']/config/name",
                name,
            )
            sess.set_item(
                f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status",
                "up",
            )
            sess.apply_changes()


class TestConcurrentAccess(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

    async def test_concurrent_update(self):
        self.sonic = MockSONiC()
        self.if_server = InterfaceServer(self.conn, self.sonic, [])
        ataish = mock.AsyncMock()
        ataish.list.return_value = {"piu1": None}

        def noop():
            pass

        ataish.close = noop

        taish = mock.MagicMock()
        module = taish.get_module.return_value
        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        with (
            mock.patch("taish.AsyncClient", return_value=ataish),
            mock.patch("taish.Client", return_value=taish),
        ):
            self.xp_server = TransponderServer(self.conn, "127.0.0.1:50051")

            async def event_handler(*args):
                await asyncio.sleep(10)

            self.if_server.event_handler = event_handler

            servers = [self.if_server, self.xp_server]

            tasks = list(
                asyncio.create_task(c)
                for c in itertools.chain.from_iterable(
                    [await s.start() for s in servers]
                )
            )

            await asyncio.gather(
                to_subprocess(update_if),
                to_subprocess(update_xp),
            )

            await self.xp_server.stop()
            self.if_server.stop()

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
