"""Library for tests for translator services."""


import unittest
import json
import asyncio
import logging
import time
from multiprocessing import Process, Queue
from queue import Empty
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.util import call


def load_configuration_file(configuration_file):
    try:
        with open(configuration_file, "r") as f:
            return json.loads(f.read())
    except json.decoder.JSONDecodeError as e:
        raise e
    except FileNotFoundError as e:
        raise e


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

    def oper_cb(self, xpath, priv):
        interfaces = [
            {
                "name": "Interface1/1/1",
                "config": {"name": "Interface1/1/1"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "PAM4",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu1", "host-interface": "0"}
                },
            },
            {
                "name": "Interface1/1/2",
                "config": {"name": "Interface1/1/2"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "PAM4",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu1", "host-interface": "0"}
                },
            },
            {
                "name": "Interface1/1/5",
                "config": {"name": "Interface1/1/5"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "PAM4",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu2", "host-interface": "0"}
                },
            },
            {
                "name": "Interface2/1/1",
                "config": {"name": "Interface2/1/1"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "NRZ",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu3", "host-interface": "0"}
                },
            },
            {
                "name": "Interface2/1/5",
                "config": {"name": "Interface2/1/5"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "NRZ",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu4", "host-interface": "0"}
                },
            },
            {
                "name": "Interface2/1/8",
                "config": {"name": "Interface2/1/8"},
                "state": {
                    "admin-status": "DOWN",
                    "pin-mode": "PAM4",
                    "oper-status": "DOWN",
                    "associated-gearbox": "1",
                    "is-connected": False,
                },
                "ethernet": {
                    "state": {"mtu": 10000, "fec": "RS", "speed": "SPEED_100G"},
                    "synce": {
                        "state": {
                            "tx-timing-mode": "auto",
                            "current-tx-timing-mode": "external",
                        }
                    },
                },
                "component-connection": {
                    "transponder": {"module": "piu4", "host-interface": "0"}
                },
            },
        ]
        return {"interfaces": {"interface": interfaces}}


class MockGSPlatformServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-platform")
        self.handlers = {}

    def oper_cb(self, xpath, priv):
        # mock goldstone-platform data here
        components = [
            {
                "name": "SYS",
                "state": {"type": "SYS"},
                "sys": {
                    "state": {
                        "onie-info": {
                            "vendor": "test_vendor",
                            "part-number": "test_part-number",
                            "serial-number": "test_serial-number",
                        }
                    }
                },
            },
            {
                "name": "PSU1",
                "state": {"type": "PSU"},
                "psu": {
                    "state": {"model": "PSU1_test_model", "serial": "PSU1_test_serial"}
                },
            },
            {
                "name": "PSU2",
                "state": {"type": "PSU"},
                "psu": {
                    "state": {"model": "PSU2_test_model", "serial": "PSU2_test_serial"}
                },
            },
            # incomplete data
            {
                "name": "PSU3",
                "state": {"type": "PSU"},
                "psu": {"state": {"serial": None}},
            },
            {
                "name": "port1",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {
                    "state": {
                        "presence": "PRESENT",
                        "model": "transceiver_test_model_1",
                        "serial": "transceiver_test_serial_1",
                        "vendor": "transceiver_test_vendor_1",
                    }
                },
            },
            {
                "name": "port2",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {"state": {"presence": "UNPLUGGED"}},
            },
            {
                "name": "port5",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {
                    "state": {
                        "presence": "PRESENT",
                        "model": "transceiver_test_model_5",
                        "serial": "transceiver_test_serial_5",
                    }
                },
            },
            {
                "name": "port9",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {
                    "state": {
                        "presence": "PRESENT",
                        "model": "transceiver_test_model_9",
                        "serial": "transceiver_test_serial_9",
                    }
                },
            },
            {
                "name": "port13",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {
                    "state": {
                        "presence": "PRESENT",
                        "model": "transceiver_test_model_13",
                        "serial": "transceiver_test_serial_13",
                    }
                },
            },
            {
                "name": "port16",
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {
                    "state": {
                        "presence": "PRESENT",
                        "model": "transceiver_test_model_16",
                        "serial": "transceiver_test_serial_16",
                    }
                },
            },
            {"name": "piu1", "state": {"type": "PIU"}},
            {"name": "piu2", "state": {"type": "PIU"}},
            {"name": "piu3", "state": {"type": "PIU"}},
            {"name": "piu4", "state": {"type": "PIU"}},
        ]
        return {"components": {"component": components}}


class MockGSTransponderServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-transponder")
        self.handlers = {
            "modules": {
                "module": {
                    "name": NoOp,
                    "config": {"name": NoOp},
                    "network-interface": {
                        "name": NoOp,
                        "config": {
                            "name": NoOp,
                            "output-power": NoOp,
                            "line-rate": NoOp,
                            "modulation-format": NoOp,
                            "fec-type": NoOp,
                            "tx-laser-freq": NoOp,
                            "loopback-type": NoOp,
                        },
                    },
                    "host-interface": {
                        "name": NoOp,
                        "config": {"name": NoOp, "signal-rate": NoOp, "fec-type": NoOp},
                    },
                }
            }
        }

    def oper_cb(self, xpath, priv):
        # mock goldstone-transponder data here
        modules = [
            {
                "name": "piu1",
                "state": {
                    "vendor-name": "piu1_vendor_name",
                    "vendor-part-number": "piu1_vendor_pn",
                    "vendor-serial-number": "piu1_vendor_sn",
                    "oper-status": "ready",
                },
                "network-interface": [
                    {
                        "name": "0",
                        "config": {"name": "0", "output-power": -123.456789},
                        "state": {
                            "current-output-power": -20.1,
                            "current-input-power": 70.0,
                            "current-post-voa-total-power": 12,
                            "current-pre-fec-ber": "OiIFOA==",
                        },
                    }
                ],
                "host-interface": [
                    {
                        "name": "0",
                        "config": {
                            "name": "0",
                            "signal-rate": "100-gbe",
                            "fec-type": "rs",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "100-gbe"},
                    }
                ],
            },
            {
                "name": "piu2",
                "state": {"vendor-name": "piu2_vendor_name", "oper-status": "unknown"},
                "network-interface": [
                    {"name": "0", "config": {"name": "0", "output-power": 23.4567}}
                ],
                "host-interface": [
                    {
                        "name": "0",
                        "config": {
                            "name": "0",
                            "signal-rate": "200-gbe",
                            "fec-type": "fc",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "200-gbe"},
                    },
                    {
                        "name": "1",
                        "config": {
                            "name": "1",
                            "signal-rate": "200-gbe",
                            "fec-type": "fc",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "200-gbe"},
                    },
                ],
            },
            {
                "name": "piu3",
                "state": {
                    "vendor-name": "piu3_vendor_name",
                    "vendor-serial-number": "piu3_vendor_sn",
                    "oper-status": "initialize",
                },
                "network-interface": [
                    {"name": "0", "config": {"name": "0", "output-power": 0}}
                ],
                "host-interface": [
                    {
                        "name": "0",
                        "config": {
                            "name": "0",
                            "signal-rate": "400-gbe",
                            "fec-type": "none",
                            "loopback-type": "none",
                        },
                        "state": {"signal-rate": "400-gbe"},
                    },
                    {
                        "name": "1",
                        "config": {
                            "name": "1",
                            "signal-rate": "400-gbe",
                            "fec-type": "none",
                            "loopback-type": "none",
                        },
                        "state": {"signal-rate": "400-gbe"},
                    },
                    {
                        "name": "2",
                        "config": {
                            "name": "2",
                            "signal-rate": "400-gbe",
                            "fec-type": "none",
                            "loopback-type": "none",
                        },
                        "state": {"signal-rate": "400-gbe"},
                    },
                    {
                        "name": "3",
                        "config": {
                            "name": "3",
                            "signal-rate": "400-gbe",
                            "fec-type": "none",
                            "loopback-type": "none",
                        },
                        "state": {"signal-rate": "400-gbe"},
                    },
                ],
            },
            {
                "name": "piu4",
                "state": {
                    "vendor-part-number": "piu4_vendor_pn",
                    "oper-status": "unknown",
                },
                "network-interface": [
                    {
                        # no power on this interface
                        "name": "0",
                        "config": {"name": "0"},
                    }
                ],
                "host-interface": [
                    {
                        "name": "0",
                        "config": {
                            "name": "0",
                            "signal-rate": "otu4",
                            "fec-type": "rs",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "otu4"},
                    },
                    {
                        "name": "1",
                        "config": {
                            "name": "1",
                            "signal-rate": "otu4",
                            "fec-type": "rs",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "otu4"},
                    },
                    {
                        "name": "2",
                        "config": {
                            "name": "1",
                            "signal-rate": "otu4",
                            "fec-type": "rs",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "otu4"},
                    },
                    {
                        "name": "3",
                        "config": {
                            "name": "1",
                            "signal-rate": "otu4",
                            "fec-type": "rs",
                            "loopback-type": "shallow",
                        },
                        "state": {"signal-rate": "otu4"},
                    },
                ],
            },
        ]
        return {"modules": {"module": modules}}


MOCK_SERVERS = {
    "goldstone-interfaces": MockGSInterfaceServer,
    "goldstone-platform": MockGSPlatformServer,
    "goldstone-transponder": MockGSTransponderServer,
}


def run_mock_server(q, mock_modules):
    """Run mock servers.

    A TestCase can communicate with MockServers by using a Queue.
        Stop MockServers: {"type": "stop"}
        Set operational state data of a MockServer: {"type": "set", "server": "<SERVER_NAME>", "data": "<DATA_TO_SET>"}

    Args:
        q (Queue): Queue to communicate between a TestCase and MockServers.
        mock_modules (list of str): Names of modules to mock. Keys in MOCK_SERVERS
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
        time.sleep(5)  # wait for setting up mock server

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

    async def asyncTearDown(self):
        await call(self.server.stop)
        self.tasks = [t.cancel() for t in self.tasks]
        self.conn.stop()
        self.q.put({"type": "stop"})
        self.process.join()


def setup_interface(
    conn, if_name, cp_name, type="org-openroadm-interfaces:otsi", sup_intf=None
):
    """Setup/provision required leaves for OpenROADM interface.
    Args:
        conn (SysrepoSession): Sysrepo session used to make changes.
        ori (str): Name of the OpenROADM interface to provision (opaque outside of OpenROADM)
        cp_name (str): Name of supporting-circuit-pack. Must already be provisioned.
        sup_intf (str): Name of supporting interface. Must already be provisioned.
    """
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/supporting-circuit-pack-name",
        f"{cp_name}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/type",
        type,
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/supporting-port",
        "1",
    )
    if sup_intf:
        conn.set(
            f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/supporting-interface-list",
            sup_intf,
        )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/subSlot",
        f"{cp_name}",
    )
    conn.apply()


def setup_circuit_pack(conn, cp_name, shelf="SYS", slot="1"):
    """Setup/provision required leaves for OpenROADM interface.
    Args:
        conn (SysrepoSession): Sysrepo session used to make changes.
        cp_name (str): Name of the OpenROADM circuit-pack to provision
        slot (str): Name of the slot to provision for the OpenROADM circuit-pack
        shelf (str): Name of shelf. Must already be provisioned.
    """
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/circuit-pack-type",
        "cpType",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/shelf",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/slot",
        f"{slot}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/ports[port-name='1']",
        "1",
    )
    conn.apply()


def setup_otsi_connections(conn, piu, ori, slot):
    """Sets up circuit-pack and interface for PIU.
    Args:
        conn (SysrepoSession): Connector object used to make changes.
        piu (str): Name of the piu. Used to provision OpenROADM circuit-pack.
        ori (str): Name of the OpenROADM interface to provision (opaque outside of OpenROADM).
        slot (str): Name of slot to provision for OpenROADM circuit-pack.
    """
    # setup circuit-pack
    setup_circuit_pack(conn, piu, slot=slot)

    # setup interface
    setup_interface(conn, ori, piu)


def setup_shelf_and_sys(conn):
    """Perform general shelf and SYS circuit-pack configuration
    Args:
        sess (SysrepoSession): Sysrepo session used to make changes.
    """
    # Setup basic shelf info to start with
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
        "myshelftype",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
        "inService",
    )
    conn.apply()

    # And the overall SYS circuit-pack
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']/circuit-pack-type",
        "SYScpType",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']/shelf",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']/slot",
        0,
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']/subSlot",
        0,
    )
    conn.apply()


def setup_eth_port_config(conn, slot, piu, if_name, or_port):
    """
    Perform ethernet circuit pack and interface configuration
    """
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/circuit-pack-type",
        "PIUcpType",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/shelf",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/slot",
        f"{slot}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/subSlot",
        f"{piu}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/parent-circuit-pack/circuit-pack-name",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/parent-circuit-pack/cp-slot-name",
        f"{piu}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{piu}']/ports[port-name='1']",
        1,
    )
    conn.apply()

    # Next define the portX circuit pack
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/circuit-pack-type",
        "PortXcpType",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/shelf",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/slot",
        f"{slot}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/subSlot",
        f"{or_port}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/parent-circuit-pack/circuit-pack-name",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/parent-circuit-pack/cp-slot-name",
        f"{or_port}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{or_port}']/ports[port-name='1']",
        1,
    )
    conn.apply()

    # Create the interface items.
    # Note that this interface name is meaningful only to openroadm
    # However, it must be unique within the system scope
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/type",
        "org-openroadm-interfaces:ethernetCsmacd",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/administrative-state",
        "inService",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/supporting-circuit-pack-name",
        f"{or_port}",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/supporting-port",
        1,
    )
    conn.apply()


def setup_interface_hierarchy(conn):
    """Sets up OpenROADM interface hierarchy."""

    # setup 'SYS' shelf
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
        "SYS",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
        "inService",
    )

    # setup circuit-pack and otsi interface
    setup_otsi_connections(conn, "piu1", "otsi-piu1", "1")
    conn.set(
        "/org-openroadm-device:org-openroadm-device/interface[name='otsi-piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/otsi-rate",
        "org-openroadm-common-optical-channel-types:R400G-otsi",
    )

    # setup circuit-pack and otsi-g interface
    # supporting-circuit-pack-name will be derived from supporting-interface-list for high-level-interfaces in Phase 2
    setup_interface(
        conn,
        "otsig-piu1",
        "piu1",
        type="org-openroadm-interfaces:otsi-group",
        sup_intf="otsi-piu1",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/org-openroadm-otsi-group-interfaces:otsi-group/group-rate",
        "org-openroadm-common-optical-channel-types:R400G-otsi",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/org-openroadm-otsi-group-interfaces:otsi-group/group-id",
        1,
    )

    # setup otuc interface
    setup_interface(
        conn,
        "otuc-piu1",
        "piu1",
        type="org-openroadm-interfaces:otnOtu",
        sup_intf="otsig-piu1",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/rate",
        "org-openroadm-otn-common-types:OTUCn",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/otucn-n-rate",
        4,
    )

    # setup oduc interface
    setup_interface(
        conn,
        "oduc-piu1",
        "piu1",
        type="org-openroadm-interfaces:otnOdu",
        sup_intf="otuc-piu1",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/rate",
        "org-openroadm-otn-common-types:ODUCn",
    )
    conn.set(
        f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/oducn-n-rate",
        4,
    )

    conn.apply()
