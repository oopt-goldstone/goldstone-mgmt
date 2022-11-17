"""Tests of the cache feature for OpenConfig translators."""

# pylint: disable=W0212

import unittest
import time
from goldstone.xlate.openconfig.cache import InMemoryCache, CacheDataNotExistError
from goldstone.xlate.openconfig.cache_updater import CacheUpdater
from tests.lib import XlateTestCase, load_operational_modes

operational_modes = load_operational_modes()


class TestInMemoryCache(unittest.TestCase):
    """Tests for InMemoryCache."""

    def test_get(self):
        inmemory_cache = InMemoryCache()
        data = {
            "interfaces": {
                "interface": [
                    {"name": "Ethernet1/0/1", "state": {"oper-status": "UP"}},
                    {"name": "Ethernet1/0/2", "state": {"oper-status": "DOWN"}},
                ]
            }
        }
        inmemory_cache._data["openconfig-interfaces"] = data
        self.assertEqual(inmemory_cache.get("openconfig-interfaces"), data)

    def test_get_not_exist(self):
        inmemory_cache = InMemoryCache()
        with self.assertRaises(CacheDataNotExistError):
            inmemory_cache.get("openconfig-interfaces")

    def test_set(self):
        inmemory_cache = InMemoryCache()
        data = {
            "interfaces": {
                "interface": [
                    {"name": "Ethernet1/0/1", "state": {"oper-status": "UP"}},
                    {"name": "Ethernet1/0/2", "state": {"oper-status": "DOWN"}},
                ]
            }
        }
        inmemory_cache.set("openconfig-interfaces", data)
        self.assertEqual(inmemory_cache._data["openconfig-interfaces"], data)

    def test_set_exist(self):
        inmemory_cache = InMemoryCache()
        data = {
            "interfaces": {
                "interface": [
                    {"name": "Ethernet1/0/1", "state": {"oper-status": "UP"}},
                    {"name": "Ethernet1/0/2", "state": {"oper-status": "DOWN"}},
                ]
            }
        }
        inmemory_cache._data["openconfig-interfaces"] = data
        updated_data = {
            "interfaces": {
                "interface": [
                    {"name": "Ethernet1/0/1", "state": {"oper-status": "DOWN"}},
                    {"name": "Ethernet1/0/2", "state": {"oper-status": "UP"}},
                ]
            }
        }
        inmemory_cache.set("openconfig-interfaces", updated_data)
        self.assertEqual(inmemory_cache._data["openconfig-interfaces"], updated_data)


class TestCacheUpdater(XlateTestCase):
    """Tests for CacheUpdater."""

    MOCK_MODULES = [
        "goldstone-interfaces",
        "goldstone-platform",
        "goldstone-transponder",
        "goldstone-gearbox",
        "goldstone-system",
    ]
    CACHE_DATASTORE = InMemoryCache
    CACHE_UPDATER = CacheUpdater
    WAIT_MOCK = 2

    async def test_create_cache_interfaces(self):
        mock_data_interfaces = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {
                            "name": "Ethernet1/0/1",
                            "description": "Ethernet interface.",
                            "admin-status": "UP",
                            "oper-status": "UP",
                            "counters": {
                                "in-octets": 1000,
                                "in-unicast-pkts": 100,
                                "in-broadcast-pkts": 200,
                                "in-multicast-pkts": 300,
                                "in-discards": 400,
                                "in-errors": 500,
                                "in-unknown-protos": 600,
                                "out-octets": 2000,
                                "out-unicast-pkts": 100,
                                "out-broadcast-pkts": 200,
                                "out-multicast-pkts": 300,
                                "out-discards": 400,
                                "out-errors": 500,
                            },
                        },
                        "ethernet": {
                            "state": {
                                "mtu": 10000,
                                "fec": "RS",
                            }
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    },
                    {
                        "name": "Ethernet1/0/2",
                        "state": {
                            "name": "Ethernet1/0/2",
                            "description": "Ethernet interface.",
                            "admin-status": "DOWN",
                            "oper-status": "DOWN",
                        },
                        "ethernet": {
                            "state": {
                                "mtu": 10000,
                                "fec": "NONE",
                            }
                        },
                        "component-connection": {"platform": {"component": "port2"}},
                    },
                    {
                        "name": "Ethernet1/1/1",
                        "state": {
                            "name": "Ethernet1/1/1",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "1",
                            }
                        },
                    },
                    {
                        "name": "Ethernet1/1/2",
                        "state": {
                            "name": "Ethernet1/1/2",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "2",
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interfaces)
        mock_data_platform = {
            "components": {
                "component": [
                    {
                        "name": "port1",
                        "state": {
                            "name": "port1",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                    {
                        "name": "port2",
                        "state": {
                            "name": "port2",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                            "localtion": "1",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "400g",
                                    "modulation-format": "dp-16-qam",
                                    "fec-type": "ofec",
                                    "client-signal-mapping-type": "flexo-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "host-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "index": 1,
                                    "signal-rate": "100-gbe",
                                },
                            },
                            {
                                "name": "2",
                                "state": {
                                    "name": "2",
                                    "index": 2,
                                    "signal-rate": "100-gbe",
                                },
                            },
                        ],
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        mock_data_gearbox = {
            "gearboxes": {
                "gearbox": [
                    {
                        "name": "1",
                        "state": {
                            "name": "1",
                        },
                        "connections": {
                            "connection": [
                                {
                                    "client-interface": "Ethernet1/0/1",
                                    "line-interface": "Ethernet1/1/1",
                                },
                                {
                                    "client-interface": "Ethernet1/0/2",
                                    "line-interface": "Ethernet1/1/2",
                                },
                            ]
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-gearbox", mock_data_gearbox)

        def test():
            time.sleep(self.WAIT_MOCK)  # wait for the mock server and cache updating
            data = self.cache_updater._cache.get("openconfig-interfaces")
            expected = {
                "interfaces": {
                    "interface": [
                        {
                            "name": "Ethernet1/0/1",
                            "state": {
                                "name": "Ethernet1/0/1",
                                "type": "iana-if-type:ethernetCsmacd",
                                "mtu": 10000,
                                "description": "Ethernet interface.",
                                "enabled": True,
                                "admin-status": "UP",
                                "oper-status": "UP",
                                "counters": {
                                    "in-octets": 1000,
                                    "in-pkts": 2100,
                                    "in-unicast-pkts": 100,
                                    "in-broadcast-pkts": 200,
                                    "in-multicast-pkts": 300,
                                    "in-discards": 400,
                                    "in-errors": 500,
                                    "in-unknown-protos": 600,
                                    "out-octets": 2000,
                                    "out-pkts": 1500,
                                    "out-unicast-pkts": 100,
                                    "out-broadcast-pkts": 200,
                                    "out-multicast-pkts": 300,
                                    "out-discards": 400,
                                    "out-errors": 500,
                                },
                                "hardware-port": "client-port1",
                            },
                            "ethernet": {
                                "state": {
                                    "fec-mode": "FEC_RS528",
                                },
                            },
                        },
                        {
                            "name": "Ethernet1/0/2",
                            "state": {
                                "name": "Ethernet1/0/2",
                                "type": "iana-if-type:ethernetCsmacd",
                                "mtu": 10000,
                                "description": "Ethernet interface.",
                                "enabled": False,
                                "admin-status": "DOWN",
                                "oper-status": "DOWN",
                                "hardware-port": "client-port2",
                            },
                            "ethernet": {
                                "state": {
                                    "fec-mode": "FEC_DISABLED",
                                },
                            },
                        },
                        {
                            "name": "Ethernet1/1/1",
                            "state": {
                                "name": "Ethernet1/1/1",
                                "type": "iana-if-type:ethernetCsmacd",
                            },
                        },
                        {
                            "name": "Ethernet1/1/2",
                            "state": {
                                "name": "Ethernet1/1/2",
                                "type": "iana-if-type:ethernetCsmacd",
                            },
                        },
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_create_cache_platform(self):
        mock_data_platform = {
            "components": {
                "component": [
                    {
                        "name": "SYS",
                        "state": {
                            "type": "SYS",
                            "id": 1,
                            "description": "System Information",
                        },
                        "sys": {
                            "state": {
                                "onie-info": {
                                    "manufacturer": "Manufacturer",
                                    "serial-number": "Serial number",
                                    "part-number": "Part number",
                                }
                            }
                        },
                    },
                    {
                        "name": "THERMAL SENSOR1",
                        "state": {"type": "THERMAL"},
                        "thermal": {"state": {"temperature": 10000}},
                    },
                    {
                        "name": "THERMAL SENSOR2",
                        "state": {"type": "THERMAL"},
                        "thermal": {"state": {"temperature": 20000}},
                    },
                    {
                        "name": "port1",
                        "state": {
                            "name": "port1",
                            "type": "TRANSCEIVER",
                            "id": 200,
                            "description": "QSFP-28 transceiver information.",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                                "vendor": "Vendor Name",
                                "serial": "Serial number",
                                "model": "Model number",
                            }
                        },
                    },
                    {
                        "name": "fan",
                        "state": {
                            "name": "fan",
                            "type": "FAN",
                            "id": 300,
                            "description": "Fan information.",
                        },
                        "fan": {"state": {"fan-state": "PRESENT", "status": "RUNNING"}},
                    },
                    {
                        "name": "power supply",
                        "state": {
                            "name": "power supply",
                            "type": "PSU",
                            "id": 400,
                            "description": "PSU information.",
                        },
                        "psu": {
                            "state": {
                                "psu-state": "PRESENT",
                                "status": "RUNNING",
                                "serial": "Serial number",
                                "model": "Model number",
                                "output-power": 50000,
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
        mock_data_system = {
            "system": {"state": {"software-version": "Software version"}}
        }
        self.set_mock_oper_data("goldstone-system", mock_data_system)
        mock_data_interface = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {
                            "name": "Ethernet1/0/1",
                            "oper-status": "UP",
                            "admin-status": "UP",
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    },
                    {
                        "name": "Ethernet1/1/1",
                        "state": {
                            "name": "Ethernet1/1/1",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "1",
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interface)
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                            "oper-status": "ready",
                            "id": 100,
                            "description": "CFP2-DCO module information.",
                            "vendor-name": "Vendor Name",
                            "firmware-version": "Firmware Version",
                            "vendor-serial-number": "Vendor Serial number",
                            "vendor-part-number": "Vendor Part number",
                            "location": "1",
                            "temp": 1.3372036854775807,
                            "admin-status": "up",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "oper-status": "ready",
                                    "id": 10,
                                    "description": "CFP2-DCO network-interface information.",
                                    "index": 1,
                                    "current-chromatic-dispersion": 2000,
                                    "current-input-power": 1.3372036854775807,
                                    "current-output-power": 2.3372036854775807,
                                    "tx-laser-freq": 100000000,
                                    "output-power": 3.3372036854775807,
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "sc-fec",
                                    "client-signal-mapping-type": "otu4-lr",
                                },
                            }
                        ],
                        "host-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "index": 1,
                                    "signal-rate": "100-gbe",
                                },
                            },
                        ],
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)
        mock_data_gearbox = {
            "gearboxes": {
                "gearbox": [
                    {
                        "name": "1",
                        "state": {
                            "name": "1",
                        },
                        "connections": {
                            "connection": [
                                {
                                    "client-interface": "Ethernet1/0/1",
                                    "line-interface": "Ethernet1/1/1",
                                },
                            ]
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-gearbox", mock_data_gearbox)

        def test():
            time.sleep(self.WAIT_MOCK)  # wait for the mock server and cache updating
            data = self.cache_updater._cache.get("openconfig-platform")
            expected = {
                "components": {
                    "component": [
                        {
                            "name": "CHASSIS",
                            "state": {
                                "name": "CHASSIS",
                                "type": "openconfig-platform-types:CHASSIS",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "1",
                                "description": "System Information",
                                "mfg-name": "Manufacturer",
                                "software-version": "Software version",
                                "serial-no": "Serial number",
                                "part-no": "Part number",
                                "temperature": {"instant": 10.0},
                                "removable": False,
                            },
                            "subcomponents": {
                                "subcomponent": [
                                    {
                                        "name": "line-piu1",
                                        "state": {"name": "line-piu1"},
                                    },
                                    {
                                        "name": "client-port1",
                                        "state": {"name": "client-port1"},
                                    },
                                    {"name": "fan", "state": {"name": "fan"}},
                                    {
                                        "name": "power supply",
                                        "state": {"name": "power supply"},
                                    },
                                ]
                            },
                        },
                        {
                            "name": "line-piu1",
                            "state": {
                                "name": "line-piu1",
                                "type": "openconfig-platform-types:PORT",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "100",
                                "description": "CFP2-DCO module information.",
                                "location": "1",
                                "parent": "CHASSIS",
                                "removable": False,
                            },
                            "subcomponents": {
                                "subcomponent": [
                                    {
                                        "name": "transceiver-line-piu1",
                                        "state": {"name": "transceiver-line-piu1"},
                                    }
                                ]
                            },
                            "port": {
                                "optical-port": {
                                    "state": {
                                        "admin-state": "ENABLED",
                                        "optical-port-type": "openconfig-transport-types:TERMINAL_LINE",
                                    }
                                }
                            },
                        },
                        {
                            "name": "transceiver-line-piu1",
                            "state": {
                                "name": "transceiver-line-piu1",
                                "type": "openconfig-platform-types:TRANSCEIVER",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "100",
                                "description": "CFP2-DCO module information.",
                                "mfg-name": "Vendor Name",
                                "software-version": "Firmware Version",
                                "serial-no": "Vendor Serial number",
                                "part-no": "Vendor Part number",
                                "location": "1",
                                "parent": "line-piu1",
                                "temperature": {"instant": 1.3},
                                "removable": True,
                            },
                            "subcomponents": {
                                "subcomponent": [
                                    {
                                        "name": "och-transceiver-line-piu1-1",
                                        "state": {
                                            "name": "och-transceiver-line-piu1-1"
                                        },
                                    }
                                ]
                            },
                        },
                        {
                            "name": "och-transceiver-line-piu1-1",
                            "state": {
                                "name": "och-transceiver-line-piu1-1",
                                "type": "openconfig-transport-types:OPTICAL_CHANNEL",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "10",
                                "description": "CFP2-DCO network-interface information.",
                                "location": "1",
                                "parent": "transceiver-line-piu1",
                                "removable": False,
                            },
                            "optical-channel": {
                                "state": {
                                    "chromatic-dispersion": {"instant": 2000.0},
                                    "input-power": {"instant": 1.34},
                                    "output-power": {"instant": 2.34},
                                    "frequency": 100,
                                    "target-output-power": 3.34,
                                    "operational-mode": 100,
                                }
                            },
                            "properties": {
                                "property": [
                                    {
                                        "name": "CROSS_CONNECTION",
                                        "state": {
                                            "name": "CROSS_CONNECTION",
                                            "value": "PRESET",
                                        },
                                    },
                                    {
                                        "name": "latency",
                                        "state": {"name": "latency", "value": None},
                                    },
                                ]
                            },
                        },
                        {
                            "name": "client-port1",
                            "state": {
                                "name": "client-port1",
                                "type": "openconfig-platform-types:PORT",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "200",
                                "description": "QSFP-28 transceiver information.",
                                "parent": "CHASSIS",
                                "removable": False,
                            },
                            "subcomponents": {
                                "subcomponent": [
                                    {
                                        "name": "transceiver-client-port1",
                                        "state": {"name": "transceiver-client-port1"},
                                    }
                                ]
                            },
                            "port": {
                                "optical-port": {
                                    "state": {
                                        "admin-state": "ENABLED",
                                        "optical-port-type": "openconfig-transport-types:TERMINAL_CLIENT",
                                    }
                                }
                            },
                        },
                        {
                            "name": "transceiver-client-port1",
                            "state": {
                                "name": "transceiver-client-port1",
                                "type": "openconfig-platform-types:TRANSCEIVER",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "200",
                                "description": "QSFP-28 transceiver information.",
                                "mfg-name": "Vendor Name",
                                "serial-no": "Serial number",
                                "part-no": "Model number",
                                "parent": "client-port1",
                                "removable": True,
                            },
                        },
                        {
                            "name": "fan",
                            "state": {
                                "name": "fan",
                                "type": "openconfig-platform-types:FAN",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "300",
                                "description": "Fan information.",
                                "parent": "CHASSIS",
                            },
                        },
                        {
                            "name": "power supply",
                            "state": {
                                "name": "power supply",
                                "type": "openconfig-platform-types:POWER_SUPPLY",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "400",
                                "description": "PSU information.",
                                "serial-no": "Serial number",
                                "part-no": "Model number",
                                "parent": "CHASSIS",
                                "used-power": 50,
                            },
                        },
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_create_cache_terminal_device(self):
        mock_data_interface = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {
                            "name": "Ethernet1/0/1",
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    },
                    {
                        "name": "Ethernet1/0/2",
                        "state": {
                            "name": "Ethernet1/0/2",
                        },
                        "component-connection": {"platform": {"component": "port2"}},
                    },
                    {
                        "name": "Ethernet1/0/3",
                        "state": {
                            "name": "Ethernet1/0/3",
                        },
                        "component-connection": {"platform": {"component": "port3"}},
                    },
                    {
                        "name": "Ethernet1/0/4",
                        "state": {
                            "name": "Ethernet1/0/4",
                        },
                        "component-connection": {"platform": {"component": "port4"}},
                    },
                    {
                        "name": "Ethernet1/1/1",
                        "state": {
                            "name": "Ethernet1/1/1",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "1",
                            }
                        },
                    },
                    {
                        "name": "Ethernet1/1/2",
                        "state": {
                            "name": "Ethernet1/1/2",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "2",
                            }
                        },
                    },
                    {
                        "name": "Ethernet1/1/3",
                        "state": {
                            "name": "Ethernet1/1/3",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "3",
                            }
                        },
                    },
                    {
                        "name": "Ethernet1/1/4",
                        "state": {
                            "name": "Ethernet1/1/4",
                        },
                        "component-connection": {
                            "transponder": {
                                "module": "piu1",
                                "host-interface": "4",
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interface)
        mock_data_platform = {
            "components": {
                "component": [
                    {
                        "name": "port1",
                        "state": {
                            "name": "port1",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                    {
                        "name": "port2",
                        "state": {
                            "name": "port2",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                    {
                        "name": "port3",
                        "state": {
                            "name": "port3",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                    {
                        "name": "port4",
                        "state": {
                            "name": "port4",
                            "type": "TRANSCEIVER",
                        },
                        "transceiver": {
                            "state": {
                                "presence": "PRESENT",
                            }
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                            "localtion": "1",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "400g",
                                    "modulation-format": "dp-16-qam",
                                    "fec-type": "ofec",
                                    "client-signal-mapping-type": "flexo-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "host-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "index": 1,
                                    "signal-rate": "100-gbe",
                                },
                            },
                            {
                                "name": "2",
                                "state": {
                                    "name": "2",
                                    "index": 2,
                                    "signal-rate": "100-gbe",
                                },
                            },
                            {
                                "name": "3",
                                "state": {
                                    "name": "3",
                                    "index": 3,
                                    "signal-rate": "100-gbe",
                                },
                            },
                            {
                                "name": "4",
                                "state": {
                                    "name": "4",
                                    "index": 4,
                                    "signal-rate": "100-gbe",
                                },
                            },
                        ],
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)
        mock_data_gearbox = {
            "gearboxes": {
                "gearbox": [
                    {
                        "name": "1",
                        "state": {
                            "name": "1",
                        },
                        "connections": {
                            "connection": [
                                {
                                    "client-interface": "Ethernet1/0/1",
                                    "line-interface": "Ethernet1/1/1",
                                },
                                {
                                    "client-interface": "Ethernet1/0/2",
                                    "line-interface": "Ethernet1/1/2",
                                },
                                {
                                    "client-interface": "Ethernet1/0/3",
                                    "line-interface": "Ethernet1/1/3",
                                },
                                {
                                    "client-interface": "Ethernet1/0/4",
                                    "line-interface": "Ethernet1/1/4",
                                },
                            ]
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-gearbox", mock_data_gearbox)

        def test():
            time.sleep(self.WAIT_MOCK)  # wait for the mock server and cache updating
            data = self.cache_updater._cache.get("openconfig-terminal-device")
            expected = {
                "terminal-device": {
                    "logical-channels": {
                        "channel": [
                            # Client signal for client-port1
                            {
                                "index": 0,
                                "state": {
                                    "index": 0,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                                },
                                "ingress": {
                                    "state": {
                                        "transceiver": "transceiver-client-port1",
                                    },
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 1,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Lower order ODU for client-port1
                            {
                                "index": 1,
                                "state": {
                                    "index": 1,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 8,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Client signal for client-port2
                            {
                                "index": 2,
                                "state": {
                                    "index": 2,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                                },
                                "ingress": {
                                    "state": {
                                        "transceiver": "transceiver-client-port2",
                                    },
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 3,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Lower order ODU for client-port2
                            {
                                "index": 3,
                                "state": {
                                    "index": 3,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 8,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Client signal for client-port3
                            {
                                "index": 4,
                                "state": {
                                    "index": 4,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                                },
                                "ingress": {
                                    "state": {
                                        "transceiver": "transceiver-client-port3",
                                    },
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 5,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Lower order ODU for client-port3
                            {
                                "index": 5,
                                "state": {
                                    "index": 5,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 8,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Client signal for client-port4
                            {
                                "index": 6,
                                "state": {
                                    "index": 6,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                                },
                                "ingress": {
                                    "state": {
                                        "transceiver": "transceiver-client-port4",
                                    },
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 7,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Lower order ODU for client-port4
                            {
                                "index": 7,
                                "state": {
                                    "index": 7,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 8,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 100.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # Higher order ODU for och-transceiver-line-piu1-1
                            {
                                "index": 8,
                                "state": {
                                    "index": 8,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_400G",
                                    "trib-protocol": "openconfig-transport-types:PROT_ODUCN",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "LOGICAL_CHANNEL",
                                                "logical-channel": 9,
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 400.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                            # OTU for och-transceiver-line-piu1-1
                            {
                                "index": 9,
                                "state": {
                                    "index": 9,
                                    "description": "",
                                    "admin-state": "ENABLED",
                                    "rate-class": "openconfig-transport-types:TRIB_RATE_400G",
                                    "trib-protocol": "openconfig-transport-types:PROT_OTUCN",
                                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                                },
                                "otn": {
                                    "state": {
                                        "tributary-slot-granularity": "openconfig-transport-types:TRIB_SLOT_5G",
                                        "pre-fec-ber": {
                                            "instant": "0.000618058722466230",
                                            "interval": 1000000000,
                                        },
                                    }
                                },
                                "logical-channel-assignments": {
                                    "assignment": [
                                        {
                                            "index": 0,
                                            "state": {
                                                "index": 0,
                                                "assignment-type": "OPTICAL_CHANNEL",
                                                "optical-channel": "och-transceiver-line-piu1-1",
                                                "mapping": "openconfig-transport-types:GMP",
                                                "allocation": 400.000,
                                                "tributary-slot-index": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                        ]
                    },
                    "operational-modes": {
                        "mode": [
                            {
                                "mode-id": 100,
                                "state": {
                                    "mode-id": 100,
                                    "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                            {
                                "mode-id": 101,
                                "state": {
                                    "mode-id": 101,
                                    "description": "100G, DP-QPSK, oFEC, FlexO-LR, 31.6GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                            {
                                "mode-id": 200,
                                "state": {
                                    "mode-id": 200,
                                    "description": "200G, DP-16QAM, oFEC, FlexO-LR, 31.6GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                            {
                                "mode-id": 201,
                                "state": {
                                    "mode-id": 201,
                                    "description": "200G, DP-QPSK, oFEC, FlexO-LR, 63.1GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                            {
                                "mode-id": 300,
                                "state": {
                                    "mode-id": 300,
                                    "description": "300G, DP-8QAM, oFEC, FlexO-LR, 63.1GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                            {
                                "mode-id": 400,
                                "state": {
                                    "mode-id": 400,
                                    "description": "400G, DP-16QAM, oFEC, FlexO-LR, 63.1GHz",
                                    "vendor-id": "example vendor",
                                },
                            },
                        ]
                    },
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
