"""Tests of gNMI server."""

# pylint: disable=W0212,C0103

import unittest
import logging
import os
import json
from multiprocessing import Process, Queue
import asyncio
import grpc_testing
import libyang
from goldstone.lib.core import ServerBase
from goldstone.lib.connector.sysrepo import Connector
from goldstone.north.gnmi.server import gNMIServicer
from goldstone.north.gnmi.repo.repo import Repository
from goldstone.north.gnmi.repo.sysrepo import Sysrepo
from goldstone.north.gnmi.proto import gnmi_pb2


def load_supported_models():
    with open(os.path.dirname(__file__) + "/gnmi-supported-models.json", "r") as f:
        supported_models = json.load(f)
    return supported_models


class MockRepository(Repository):
    def __init__(self, data=None, exception=None):
        self.data = data
        self.exception = exception

    def get(self, xpath, strip=True):
        result = libyang.xpath_get(self.data, xpath, filter=False)
        return result

    def set(self, xpath, data):
        if self.exception is not None:
            raise self.exception

    def delete(self, xpath):
        if self.exception is not None:
            raise self.exception


class MockServer(ServerBase):
    """MockServer is mock handler server for tests.

    Attributes:
        oper_data (dict): Data for oper_cb() to return. You can set this to configure mock's behavior.
    """

    def __init__(self, conn, module):
        super().__init__(conn, module)
        self.oper_data = {}
        self.notifs_xpath = ""
        self.notifs_data = {}
        self.handlers = {}

    async def change_cb(self, event, req_id, changes, priv):
        pass

    def oper_cb(self, xpath, priv):
        return self.oper_data

    def notify(self, xpath, data):
        self.conn.send_notification(xpath, data)

    def send_notifs(self):
        for data in self.notifs_data:
            self.notify(self.notifs_xpath, data)


class MockOCPlatformServer(MockServer):
    """MockOCPlatformServer is mock handler server for openconfig-platform."""

    def __init__(self, conn, module):
        super().__init__(conn, module)
        # You can customize the behavior of the mock server.
        self.oper_data = {}
        self.handlers = {}


class MockOCInterfacesServer(MockServer):
    """MockOCInterfacesServer is mock handler server for openconfig-interfaces models."""

    def __init__(self, conn, module):
        super().__init__(conn, module)
        # You can customize the behavior of the mock server.
        self.oper_data = {}
        self.handlers = {}


class MockOCTerminalDeviceServer(MockServer):
    """MockOCTerminalDeviceServer is mock handler server for openconfig-terminal-device ."""

    def __init__(self, conn, module):
        super().__init__(conn, module)
        # You can customize the behavior of the mock server.
        self.oper_data = {}
        self.handlers = {}


class MockGSTelemetryServer(MockServer):
    """MockGSTelemetryServer is mock handler server for goldstone-telemetry."""

    def __init__(self, conn, module):
        super().__init__(conn, module)
        # You can customize the behavior of the mock server.
        self.oper_data = {}
        self.handlers = {}
        self.poll_count = 0
        self.conn.subscribe_rpc_call("/goldstone-telemetry:poll", self.poll_cb)

    def poll_cb(self, xpath, inputs, event, priv):
        self.send_notifs()


MOCK_SERVERS = {
    "openconfig-platform": MockOCPlatformServer,
    "openconfig-interfaces": MockOCInterfacesServer,
    "openconfig-terminal-device": MockOCTerminalDeviceServer,
    "goldstone-telemetry": MockGSTelemetryServer,
}


def run_mock_server(q, mock_modules):
    conn = Connector()
    servers = {}
    for mock_module in mock_modules:
        servers[mock_module] = MOCK_SERVERS[mock_module](conn, mock_module)

    async def _main():
        tasks = []
        for server in servers.items():
            tasks += await server[1].start()

        async def evloop():
            while True:
                await asyncio.sleep(0.01)
                try:
                    msg = q.get(False)
                except:
                    pass
                else:
                    if msg["type"] == "stop":
                        return
                    elif msg["type"] == "set-oper-data":
                        servers[msg["server"]].oper_data = msg["data"]
                    elif msg["type"] == "set-notifs-data":
                        servers[msg["server"]].notifs_xpath = msg["path"]
                        servers[msg["server"]].notifs_data = msg["data"]
                    elif msg["type"] == "send-notif":
                        servers[msg["server"]].send_notifs()

        tasks.append(evloop())
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t) for t in tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    asyncio.run(_main())


class gNMIServerTestCase(unittest.IsolatedAsyncioTestCase):
    """Test case base class for gNMI server.

    Attributes:
        MOCK_MODULES (list): Module names the server will use.
    """

    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)

        # gNMI server to test.
        self._real_time = grpc_testing.strict_real_time()
        self.target_service = gnmi_pb2.DESCRIPTOR.services_by_name["gNMI"]
        self.servicer = gNMIServicer(Sysrepo, load_supported_models())
        descriptors_to_services = {self.target_service: self.servicer}
        self._real_time_server = grpc_testing.server_from_dictionary(
            descriptors_to_services, self._real_time
        )
        self.rpc = None

        self.conn = Connector()

        for module in self.MOCK_MODULES:
            self.conn.delete_all(module)
        self.conn.apply()

        self.q = Queue()
        self.process = Process(target=run_mock_server, args=(self.q, self.MOCK_MODULES))
        self.process.start()

        self.tasks = []

    async def run_gnmi_server_test(self, test):
        """Run a test as a thread.

        Args:
            test (func): Test to run.
        """
        await asyncio.sleep(0.1)
        self.tasks.append(asyncio.to_thread(test))
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t)
            for t in self.tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    def set_mock_oper_data(self, server, data):
        """Set operational state data to the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
            data (dict): Operational state data that the server returns.
        """
        self.q.put({"type": "set-oper-data", "server": server, "data": data})

    def set_mock_notifs_data(self, server, path, data):
        """Set notifications data to the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
            path (str): Path of the notifications to send.
            data (dict): Data of the notifications to send.
        """
        self.q.put(
            {"type": "set-notifs-data", "server": server, "path": path, "data": data}
        )

    def send_mock_notifs(self, server):
        """Send notifications from the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
        """
        self.q.put({"type": "send-notif", "server": server})

    async def asyncTearDown(self):
        try:
            self.rpc.cancel()
        except Exception:
            pass
        self.servicer._subscribe_repo.stop()
        self.tasks = []
        self.conn.stop()
        self.q.put({"type": "stop"})
        self.process.join()

    def gnmi_capabilities(self, request):
        rpc = self._real_time_server.invoke_unary_unary(
            self.target_service.methods_by_name["Capabilities"], (), request, None
        )
        response, trailing_metadata, code, details = rpc.termination()
        return response, code

    def gnmi_get(self, request):
        rpc = self._real_time_server.invoke_unary_unary(
            self.target_service.methods_by_name["Get"], (), request, None
        )
        response, trailing_metadata, code, details = rpc.termination()
        return response, code

    def gnmi_set(self, request):
        rpc = self._real_time_server.invoke_unary_unary(
            self.target_service.methods_by_name["Set"], (), request, None
        )
        response, trailing_metadata, code, details = rpc.termination()
        return response, code

    def gnmi_subscribe(self, request):
        rpc = self._real_time_server.invoke_stream_stream(
            self.target_service.methods_by_name["Subscribe"], (), None
        )
        rpc.send_request(request)
        return rpc
