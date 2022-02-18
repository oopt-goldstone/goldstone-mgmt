"""Tests of OpenConfig translater for openconfig-terminal-device."""


import unittest
from libyang.keyed_list import KeyedList
from goldstone.xlate.openconfig.terminal_device import (
    TerminalDeviceServer,
    OperationalModeFactory,
    LogicalChannelFactory,
)
from goldstone.xlate.openconfig.platform import ComponentFactory, ComponentNameResolver
from tests.lib import load_operational_modes, XlateTestCase


operational_modes = load_operational_modes()


class TestOperationalModeFactory(unittest.TestCase):
    """Tests for OperationalModeFactory."""

    def test_one_mode(self):
        config = {
            1: {
                "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                "vendor-id": "example vendor",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "sc-fec",
                "client-signal-mapping": "otu4-lr",
            }
        }
        omf = OperationalModeFactory(config)
        data = omf.create({})
        expected = [
            {
                "mode-id": 1,
                "state": {
                    "mode-id": 1,
                    "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                    "vendor-id": "example vendor",
                },
            }
        ]
        self.assertEqual(data, expected)

    def test_two_modes(self):
        config = {
            1: {
                "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                "vendor-id": "example vendor",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "sc-fec",
                "client-signal-mapping": "otu4-lr",
            },
            2: {
                "description": "100G, DP-QPSK, oFEC, FlexO-LR, 31.6GHz",
                "vendor-id": "example vendor",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "ofec",
                "client-signal-mapping": "flexo-lr",
            },
        }
        omf = OperationalModeFactory(config)
        data = omf.create({})
        expected = [
            {
                "mode-id": 1,
                "state": {
                    "mode-id": 1,
                    "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                    "vendor-id": "example vendor",
                },
            },
            {
                "mode-id": 2,
                "state": {
                    "mode-id": 2,
                    "description": "100G, DP-QPSK, oFEC, FlexO-LR, 31.6GHz",
                    "vendor-id": "example vendor",
                },
            },
        ]
        self.assertEqual(data, expected)

    def test_invalid_mode(self):
        config = {1: {}}
        omf = OperationalModeFactory(config)
        data = omf.create({})
        expected = []
        self.assertEqual(data, expected)

    def test_one_mode_with_invalid_mode(self):
        config = {
            1: {
                "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                "vendor-id": "example vendor",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "sc-fec",
                "client-signal-mapping": "otu4-lr",
            },
            2: {},
        }
        omf = OperationalModeFactory(config)
        data = omf.create({})
        expected = [
            {
                "mode-id": 1,
                "state": {
                    "mode-id": 1,
                    "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                    "vendor-id": "example vendor",
                },
            }
        ]
        self.assertEqual(data, expected)

    def test_create_twice(self):
        config = {
            1: {
                "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                "vendor-id": "example vendor",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "sc-fec",
                "client-signal-mapping": "otu4-lr",
            }
        }
        omf = OperationalModeFactory(config)
        data = omf.create({})
        expected = [
            {
                "mode-id": 1,
                "state": {
                    "mode-id": 1,
                    "description": "100G, DP-QPSK, SC-FEC, OTU4-LR, 28.0GHz",
                    "vendor-id": "example vendor",
                },
            }
        ]
        self.assertEqual(data, expected)
        data = omf.create({})
        self.assertEqual(data, expected)


class TestLogicalChannelFactory(unittest.TestCase):
    """Tests for LogicalChannelFactory."""

    # Test patterns for logical-channel creation.
    # mapping  | client      | line | test
    # ------------------------------------------------------------------------------------
    # otu4-lr  | 1x 100-gbe  | 100g | test_create_1x100gbe_client_100g_line_odu
    # flexo-lr | 1x 100-gbe  | 100g | test_create_1x100gbe_client_100g_line_flexo
    # flexo-lr | 2x 100-gbe  | 200g | test_create_2x100gbe_client_200g_line
    # flexo-lr | 4x 100-gbe  | 400g | test_create_4x100gbe_client_400g_line
    # flexo-lr | 1x 200-gbe  | 200g | NOTE: OpenConfig does not support PROT_200GE.
    # flexo-lr | 2x 200-gbe  | 400g | NOTE: OpenConfig does not support PROT_200GE.
    # flexo-lr | 1x 400-gbe  | 400g | test_create_1x400gbe_client_400g_line
    def test_create_1x100gbe_client_100g_line_odu(self):
        gs_components = KeyedList(
            [
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
                        }
                    },
                },
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "sc-fec",
                                    "client-signal-mapping-type": "otu4-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
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
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
                                "logical-channel": 2,
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
                "index": 2,
                "state": {
                    "index": 2,
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
                                "logical-channel": 3,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # OTU for och-transceiver-line-piu1-1
            {
                "index": 3,
                "state": {
                    "index": 3,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_OTU4",
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
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
        ]
        self.assertEqual(data, expected)

    def test_create_1x100gbe_client_100g_line_flexo(self):
        gs_components = KeyedList(
            [
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
                        }
                    },
                },
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "ofec",
                                    "client-signal-mapping-type": "flexo-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
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
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
                                "logical-channel": 2,
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
                "index": 2,
                "state": {
                    "index": 2,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
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
                                "logical-channel": 3,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # OTU for och-transceiver-line-piu1-1
            {
                "index": 3,
                "state": {
                    "index": 3,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
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
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
        ]
        self.assertEqual(data, expected)

    def test_create_2x100gbe_client_200g_line_flexo(self):
        gs_components = KeyedList(
            [
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
                        }
                    },
                },
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "200g",
                                    "modulation-format": "dp-16-qam",
                                    "fec-type": "ofec",
                                    "client-signal-mapping-type": "flexo-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
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
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
                                "logical-channel": 4,
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
                                "logical-channel": 4,
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
                "index": 4,
                "state": {
                    "index": 4,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_200G",
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
                                "logical-channel": 5,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 200.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # OTU for och-transceiver-line-piu1-1
            {
                "index": 5,
                "state": {
                    "index": 5,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_200G",
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
                                "allocation": 200.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
        ]
        self.assertEqual(data, expected)

    def test_create_4x100gbe_client_400g_line_flexo(self):
        gs_components = KeyedList(
            [
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
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
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
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
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
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
        self.assertEqual(data, expected)

    def test_create_1x400gbe_client_400g_line_flexo(self):
        gs_components = KeyedList(
            [
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
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
                            "presence": "UNPLUGGED",
                        }
                    },
                },
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
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
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "index": 1,
                                    "signal-rate": "400-gbe",
                                },
                            },
                            {
                                "name": "2",
                                "state": {
                                    "name": "2",
                                    "index": 2,
                                    "signal-rate": "400-gbe",
                                },
                            },
                            {
                                "name": "3",
                                "state": {
                                    "name": "3",
                                    "index": 3,
                                    "signal-rate": "400-gbe",
                                },
                            },
                            {
                                "name": "4",
                                "state": {
                                    "name": "4",
                                    "index": 4,
                                    "signal-rate": "400-gbe",
                                },
                            },
                        ],
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
            # Client signal for client-port1
            {
                "index": 0,
                "state": {
                    "index": 0,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_400G",
                    "trib-protocol": "openconfig-transport-types:PROT_400GE",
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
                                "allocation": 400.000,
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
                    "rate-class": "openconfig-transport-types:TRIB_RATE_400G",
                    "trib-protocol": "openconfig-transport-types:PROT_ODUFLEX_CBR",
                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                },
                "logical-channel-assignments": {
                    "assignment": [
                        {
                            "index": 0,
                            "state": {
                                "index": 0,
                                "assignment-type": "LOGICAL_CHANNEL",
                                "logical-channel": 2,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 400.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Higher order ODU for och-transceiver-line-piu1-1
            {
                "index": 2,
                "state": {
                    "index": 2,
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
                                "logical-channel": 3,
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
                "index": 3,
                "state": {
                    "index": 3,
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
        self.assertEqual(data, expected)

    def test_create_4x100gbe_client_400g_line_flexo_no_transponder(self):
        gs_components = KeyedList(
            [
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
                {
                    "name": "port9",
                    "state": {
                        "name": "port9",
                        "type": "TRANSCEIVER",
                    },
                    "transceiver": {
                        "state": {
                            "presence": "PRESENT",
                        }
                    },
                },
                {
                    "name": "port10",
                    "state": {
                        "name": "port10",
                        "type": "TRANSCEIVER",
                    },
                    "transceiver": {
                        "state": {
                            "presence": "PRESENT",
                        }
                    },
                },
                {
                    "name": "port11",
                    "state": {
                        "name": "port11",
                        "type": "TRANSCEIVER",
                    },
                    "transceiver": {
                        "state": {
                            "presence": "PRESENT",
                        }
                    },
                },
                {
                    "name": "port12",
                    "state": {
                        "name": "port12",
                        "type": "TRANSCEIVER",
                    },
                    "transceiver": {
                        "state": {
                            "presence": "PRESENT",
                        }
                    },
                },
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
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
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
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
                        "name",
                    ),
                }
                # No transponder for client port 9-12.
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
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
                {
                    "name": "Ethernet2/0/1",
                    "state": {
                        "name": "Ethernet2/0/1",
                    },
                    "component-connection": {"platform": {"component": "port9"}},
                },
                {
                    "name": "Ethernet2/0/2",
                    "state": {
                        "name": "Ethernet2/0/2",
                    },
                    "component-connection": {"platform": {"component": "port10"}},
                },
                {
                    "name": "Ethernet2/0/3",
                    "state": {
                        "name": "Ethernet2/0/3",
                    },
                    "component-connection": {"platform": {"component": "port11"}},
                },
                {
                    "name": "Ethernet2/0/4",
                    "state": {
                        "name": "Ethernet2/0/4",
                    },
                    "component-connection": {"platform": {"component": "port12"}},
                },
                {
                    "name": "Ethernet2/1/1",
                    "state": {
                        "name": "Ethernet2/1/1",
                    },
                    "component-connection": {
                        "transponder": {
                            "module": "piu3",
                            "host-interface": "1",
                        }
                    },
                },
                {
                    "name": "Ethernet2/1/2",
                    "state": {
                        "name": "Ethernet2/1/2",
                    },
                    "component-connection": {
                        "transponder": {
                            "module": "piu3",
                            "host-interface": "2",
                        }
                    },
                },
                {
                    "name": "Ethernet2/1/3",
                    "state": {
                        "name": "Ethernet2/1/3",
                    },
                    "component-connection": {
                        "transponder": {
                            "module": "piu3",
                            "host-interface": "3",
                        }
                    },
                },
                {
                    "name": "Ethernet2/1/4",
                    "state": {
                        "name": "Ethernet2/1/4",
                    },
                    "component-connection": {
                        "transponder": {
                            "module": "piu3",
                            "host-interface": "4",
                        }
                    },
                },
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
                },
                {
                    "name": "2",
                    "state": {
                        "name": "2",
                    },
                    "connections": {
                        "connection": [
                            {
                                "client-interface": "Ethernet2/0/1",
                                "line-interface": "Ethernet2/1/1",
                            },
                            {
                                "client-interface": "Ethernet2/0/2",
                                "line-interface": "Ethernet2/1/2",
                            },
                            {
                                "client-interface": "Ethernet2/0/3",
                                "line-interface": "Ethernet2/1/3",
                            },
                            {
                                "client-interface": "Ethernet2/0/4",
                                "line-interface": "Ethernet2/1/4",
                            },
                        ]
                    },
                },
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
                                "logical-channel": 16,
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
                                "logical-channel": 16,
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
                                "logical-channel": 16,
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
                                "logical-channel": 16,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Client signal for client-port9
            {
                "index": 8,
                "state": {
                    "index": 8,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                },
                "ingress": {
                    "state": {
                        "transceiver": "transceiver-client-port9",
                    },
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
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Lower order ODU for client-port9
            {
                "index": 9,
                "state": {
                    "index": 9,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                },
                "logical-channel-assignments": {"assignment": []},
            },
            # Client signal for client-port10
            {
                "index": 10,
                "state": {
                    "index": 10,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                },
                "ingress": {
                    "state": {
                        "transceiver": "transceiver-client-port10",
                    },
                },
                "logical-channel-assignments": {
                    "assignment": [
                        {
                            "index": 0,
                            "state": {
                                "index": 0,
                                "assignment-type": "LOGICAL_CHANNEL",
                                "logical-channel": 11,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Lower order ODU for client-port10
            {
                "index": 11,
                "state": {
                    "index": 11,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                },
                "logical-channel-assignments": {"assignment": []},
            },
            # Client signal for client-port11
            {
                "index": 12,
                "state": {
                    "index": 12,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                },
                "ingress": {
                    "state": {
                        "transceiver": "transceiver-client-port11",
                    },
                },
                "logical-channel-assignments": {
                    "assignment": [
                        {
                            "index": 0,
                            "state": {
                                "index": 0,
                                "assignment-type": "LOGICAL_CHANNEL",
                                "logical-channel": 13,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Lower order ODU for client-port11
            {
                "index": 13,
                "state": {
                    "index": 13,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                },
                "logical-channel-assignments": {"assignment": []},
            },
            # Client signal for client-port12
            {
                "index": 14,
                "state": {
                    "index": 14,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_100GE",
                    "logical-channel-type": "openconfig-transport-types:PROT_ETHERNET",
                },
                "ingress": {
                    "state": {
                        "transceiver": "transceiver-client-port12",
                    },
                },
                "logical-channel-assignments": {
                    "assignment": [
                        {
                            "index": 0,
                            "state": {
                                "index": 0,
                                "assignment-type": "LOGICAL_CHANNEL",
                                "logical-channel": 15,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # Lower order ODU for client-port12
            {
                "index": 15,
                "state": {
                    "index": 15,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
                    "trib-protocol": "openconfig-transport-types:PROT_ODU4",
                    "logical-channel-type": "openconfig-transport-types:PROT_OTN",
                },
                "logical-channel-assignments": {"assignment": []},
            },
            # Higher order ODU for och-transceiver-line-piu1-1
            {
                "index": 16,
                "state": {
                    "index": 16,
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
                                "logical-channel": 17,
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
                "index": 17,
                "state": {
                    "index": 17,
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
        self.maxDiff = None
        self.assertEqual(data, expected)

    def test_create_twice(self):
        gs_components = KeyedList(
            [
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
            ],
            "name",
        )
        gs_modules = KeyedList(
            [
                {
                    "name": "piu1",
                    "state": {
                        "name": "piu1",
                        "localtion": "1",
                    },
                    "network-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "ofec",
                                    "client-signal-mapping-type": "flexo-lr",
                                    "current-pre-fec-ber": "OiIFOA==",
                                    "current-ber-period": 1000000,
                                },
                            },
                        ],
                        "name",
                    ),
                    "host-interface": KeyedList(
                        [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "index": 1,
                                    "signal-rate": "100-gbe",
                                },
                            },
                        ],
                        "name",
                    ),
                }
            ],
            "name",
        )
        gs_interfaces = KeyedList(
            [
                {
                    "name": "Ethernet1/0/1",
                    "state": {
                        "name": "Ethernet1/0/1",
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
            ],
            "name",
        )
        gs_gearboxes = KeyedList(
            [
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
            ],
            "name",
        )
        gs_system = {}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "gearboxes": gs_gearboxes,
            "system": gs_system,
        }
        cnr = ComponentNameResolver()
        cf = ComponentFactory(operational_modes, cnr)
        lcf = LogicalChannelFactory(cnr, cf)
        data = lcf.create(gs)
        expected = [
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
                                "logical-channel": 2,
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
                "index": 2,
                "state": {
                    "index": 2,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
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
                                "logical-channel": 3,
                                "mapping": "openconfig-transport-types:GMP",
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
            # OTU for och-transceiver-line-piu1-1
            {
                "index": 3,
                "state": {
                    "index": 3,
                    "description": "",
                    "admin-state": "ENABLED",
                    "rate-class": "openconfig-transport-types:TRIB_RATE_100G",
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
                                "allocation": 100.000,
                                "tributary-slot-index": 0,
                            },
                        }
                    ]
                },
            },
        ]
        self.assertEqual(data, expected)
        data = lcf.create(gs)
        self.assertEqual(data, expected)


class TestTerminalDeviceServer(XlateTestCase):
    """Tests for TerminalDeviceServer.

    Notes:
        - Mock servers take less than a second to complete the preparation. All test methods should wait a second after
          calling set_mock_oper_data() to start test.
    """

    XLATE_SERVER = TerminalDeviceServer
    XLATE_SERVER_OPT = [operational_modes]
    XLATE_MODULES = ["openconfig-terminal-device"]
    MOCK_MODULES = [
        "goldstone-platform",
        "goldstone-interfaces",
        "goldstone-transponder",
        "goldstone-gearbox",
    ]

    async def test_get_operational_modes(self):
        def test():
            data = self.conn.get_operational(
                "/openconfig-terminal-device:terminal-device/operational-modes",
                strip=False,
            )
            expected = {
                "terminal-device": {
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
                    }
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_logical_channels_4x100gbe_client_400g_line(self):
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
            data = self.conn.get_operational(
                "/openconfig-terminal-device:terminal-device/logical-channels",
                strip=False,
            )
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
                                            "instant": 0.000618058722466230,
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
                    }
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
