import unittest
from unittest import mock
import sysrepo
from goldstone.south.sonic.interfaces import InterfaceServer
from goldstone.south.tai.transponder import TransponderServer
import itertools
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
import os
import json
import sys


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


class TestConcurrentAccess(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = sysrepo.SysrepoConnection()

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")
            sess.replace_config({}, "goldstone-interfaces")
            sess.apply_changes()

    async def test_concurrent_update(self):

        with open(os.path.dirname(__file__) + "/platform.json") as f:
            platform_info = json.loads(f.read())

        self.sonic = MockSONiC()
        self.if_server = InterfaceServer(self.conn, self.sonic, [], platform_info)
        taish = mock.AsyncMock()
        taish.list.return_value = {"/dev/piu1": None}

        def noop():
            pass

        taish.close = noop

        module = taish.get_module.return_value
        cap = module.get_attribute_capability.return_value
        cap.min = ""
        cap.max = ""

        with (mock.patch("taish.AsyncClient", return_value=taish),):
            self.xp_server = TransponderServer(
                self.conn, "127.0.0.1:50051", platform_info
            )

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
