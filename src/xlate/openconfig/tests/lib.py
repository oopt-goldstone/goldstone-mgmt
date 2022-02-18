"""Library for tests for translator services."""


import unittest
import os
import json
import asyncio
import logging
import time
from multiprocessing import Process, Queue
from queue import Empty
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.util import call


def load_operational_modes():
    with open(
        os.path.dirname(__file__) + "/operational-modes.json", "r", encoding="utf-8"
    ) as f:
        modes = json.loads(f.read())
        parsed_modes = {}
        for mode in modes:
            try:
                parsed_modes[int(mode["openconfig"]["mode-id"])] = {
                    "vendor-id": mode["openconfig"]["vendor-id"],
                    "description": mode["description"],
                    "line-rate": mode["line-rate"],
                    "modulation-format": mode["modulation-format"],
                    "fec-type": mode["fec-type"],
                    "client-signal-mapping-type": mode["client-signal-mapping-type"],
                }
            except (KeyError, TypeError):
                pass
    return parsed_modes


class FailApplyChangeHandler(ChangeHandler):
    def apply(self, user):
        raise Exception("Failed to apply for testing.")


class MockGSServer(ServerBase):
    """MockGSServer is mock handler server for Goldstone primitive models.

    Attributes:
        oper_data (dict): Data for oper_cb() to return. You can set this to configure mock's behavior.
    """

    def __init__(self, conn, module):
        super().__init__(conn, module)
        self.oper_data = {}

    def oper_cb(self, xpath, priv):
        return self.oper_data


class MockGSInterfaceServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-interfaces")
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": NoOp,
                        "name": NoOp,
                        "description": NoOp,
                        "interface-type": NoOp,
                        "loopback-mode": NoOp,
                        "prbs-mode": NoOp,
                    },
                    "ethernet": NoOp,
                    "switched-vlan": NoOp,
                    "component-connection": NoOp,
                }
            }
        }


class MockGSPlatformServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-platform")
        self.handlers = {
            "components": {
                "component": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                    },
                }
            }
        }


class MockGSTransponderServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-transponder")
        self.handlers = {
            "modules": {
                "module": {
                    "name": NoOp,
                    "config": {"name": NoOp, "admin-status": NoOp},
                    "network-interface": {
                        "name": NoOp,
                        "config": {
                            "name": NoOp,
                            "tx-dis": NoOp,
                            "tx-laser-freq": NoOp,
                            "output-power": NoOp,
                            "line-rate": NoOp,
                            "modulation-format": NoOp,
                            "fec-type": NoOp,
                            "client-signal-mapping-type": NoOp,
                        },
                    },
                }
            }
        }


class MockGSSystemServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-system")
        self.handlers = {}


class MockGSGearboxServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-gearbox")
        self.handlers = {}


MOCK_SERVERS = {
    "goldstone-interfaces": MockGSInterfaceServer,
    "goldstone-platform": MockGSPlatformServer,
    "goldstone-transponder": MockGSTransponderServer,
    "goldstone-system": MockGSSystemServer,
    "goldstone-gearbox": MockGSGearboxServer,
}


def run_mock_server(q, mock_modules):
    """Run mock servers.

    A TestCase can communicate with MockServers by using a Queue.
        Stop MockServers: {"type": "stop"}
        Set operational state data of a MockServer: {"type": "set", "server": "<SERVER NAME>", "data": "<DATA TO SET>"}

    Args:
        q (Queue): Queue to communicate between a TestCase and MockServers.
        mock_modules (list of str): Names of modules to mock. Keys in MOCK_SERVERS.
    """
    conn = Connector()
    servers = {}
    for mock_module in mock_modules:
        servers[mock_module] = MOCK_SERVERS[mock_module](conn)

    async def _main():
        tasks = []
        for server in servers.items():
            tasks += await server[1].start()

        async def evloop():
            while True:
                await asyncio.sleep(0.01)
                try:
                    msg = q.get(block=False)
                except Empty:
                    pass
                else:
                    if msg["type"] == "stop":
                        return
                    elif msg["type"] == "set-oper-data":
                        servers[msg["server"]].oper_data = msg["data"]
                    elif msg["type"] == "set-change-handler":
                        handler = servers[msg["server"]].handlers
                        nodes = msg["path"].split("/")[1:]
                        for i, node in enumerate(nodes):
                            if i >= len(nodes) - 1:
                                handler[node] = msg["handler"]
                            else:
                                handler = handler[node]

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
    conn.stop()


class XlateTestCase(unittest.IsolatedAsyncioTestCase):
    """Test case base class for translator servers.

    Attributes:
        XLATE_SERVER (ServerBase): Server class to test.
        XLATE_SERVER_OPT (list): Arguments that will be given to the server.
        XLATE_MODULES (list): Module names the server will provide.
        MOCK_MODULES (list): Module names the server will use.
    """

    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        for module in self.MOCK_MODULES:
            self.conn.delete_all(module)
        for module in self.XLATE_MODULES:
            self.conn.delete_all(module)
        self.conn.apply()

        self.q = Queue()
        self.process = Process(target=run_mock_server, args=(self.q, self.MOCK_MODULES))
        self.process.start()

        self.server = self.XLATE_SERVER(
            self.conn, reconciliation_interval=1, *self.XLATE_SERVER_OPT
        )
        self.tasks = list(asyncio.create_task(c) for c in await self.server.start())

    async def run_xlate_test(self, test):
        """Run a test as a thread.

        Args:
            test (func): Test to run.
        """
        time.sleep(1)  # wait for the mock server
        await asyncio.create_task(asyncio.to_thread(test))

    def set_mock_oper_data(self, server, data):
        """Set operational state data to the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
            data (dict): Operational state data that the server returns.
        """
        self.q.put({"type": "set-oper-data", "server": server, "data": data})

    def set_mock_change_handler(self, server, path, handler):
        """Set ChangeHandler to the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
            path (str): Path to node that the ChangeHandler handles.
            handler (ChangeHandler): ChangeHandler to set.
        """
        self.q.put(
            {
                "type": "set-change-handler",
                "server": server,
                "path": path,
                "handler": handler,
            }
        )

    async def asyncTearDown(self):
        await call(self.server.stop)
        self.tasks = [t.cancel() for t in self.tasks]
        self.conn.stop()
        self.q.put({"type": "stop"})
        self.process.join()
