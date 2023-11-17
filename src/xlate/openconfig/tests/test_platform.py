"""Tests of OpenConfig translater for openconfig-platform."""


import unittest
import time
from multiprocessing import Process, Queue
import sysrepo
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector.sysrepo import Change
from goldstone.xlate.openconfig.platform import (
    ComponentNameResolver,
    PlatformServer,
    Chassis,
    TerminalLinePort,
    LineTransceiver,
    OpticalChannel,
    TerminalClientPort,
    ClientTransceiver,
    Fan,
    PowerSupply,
    ComponentFactory,
    PortAdminStateHandler,
    OpticalChannelFrequencyHandler,
    OpticalChannelTargetOutputPowerHandler,
    OpticalChannelOperationalModeHandler,
)
from goldstone.lib.errors import Error
from tests.lib import (
    load_operational_modes,
    XlateTestCase,
    FailApplyChangeHandler,
    run_mock_server,
)


operational_modes = load_operational_modes()


class TestPlatformComponentChassis(unittest.TestCase):
    """Tests for Chassis."""

    def test_translate_id(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
                "id": 1,
            },
        }
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "1"
        self.assertEqual(chassis.data["state"]["id"], expected)

    def test_translate_description(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
                "description": "System Information",
            },
        }
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "System Information"
        self.assertEqual(chassis.data["state"]["description"], expected)

    def test_translate_manufacturer(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
            },
            "sys": {
                "state": {
                    "onie-info": {
                        "manufacturer": "Manufacturer",
                    }
                }
            },
        }
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "Manufacturer"
        self.assertEqual(chassis.data["state"]["mfg-name"], expected)

    def test_translate_software_version(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
            },
        }
        comp_thermal = {}
        system = {"state": {"software-version": "Software version"}}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "Software version"
        self.assertEqual(chassis.data["state"]["software-version"], expected)

    def test_translate_serial_number(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
            },
            "sys": {
                "state": {
                    "onie-info": {
                        "serial-number": "Serial number",
                    }
                }
            },
        }
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "Serial number"
        self.assertEqual(chassis.data["state"]["serial-no"], expected)

    def test_translate_part_number(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
            },
            "sys": {
                "state": {
                    "onie-info": {
                        "part-number": "Part number",
                    }
                }
            },
        }
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = "Part number"
        self.assertEqual(chassis.data["state"]["part-no"], expected)

    def test_translate_temperature(self):
        comp_sys = {
            "name": "SYS",
            "state": {
                "name": "SYS",
                "type": "SYS",
            },
        }
        comp_thermal = {
            "name": "THERMAL SENSOR1",
            "state": {"name": "THERMAL SENSOR1", "type": "THERMAL"},
            "thermal": {"state": {"temperature": 56789}},
        }
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = 56.8
        self.assertEqual(chassis.data["state"]["temperature"]["instant"], expected)

    def test_translate_empty(self):
        comp_sys = {}
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.translate()
        expected = {
            "name": "CHASSIS",
            "state": {
                "name": "CHASSIS",
                "type": "openconfig-platform-types:CHASSIS",
                "oper-status": "openconfig-platform-types:ACTIVE",
                "removable": False,
            },
        }
        self.assertEqual(chassis.data, expected)

    def test_translate_none(self):
        name = "CHASSIS"
        chassis = Chassis(name, None, None, None)
        chassis.translate()
        expected = {
            "name": "CHASSIS",
            "state": {
                "name": "CHASSIS",
                "type": "openconfig-platform-types:CHASSIS",
                "oper-status": "openconfig-platform-types:ACTIVE",
                "removable": False,
            },
        }
        self.assertEqual(chassis.data, expected)

    def test_append_subcomponent(self):
        comp_sys = {}
        comp_thermal = {}
        system = {}
        name = "CHASSIS"
        module_name1 = "piu1"
        module_name2 = "piu2"
        chassis = Chassis(name, comp_sys, comp_thermal, system)
        chassis.append_subcomponent(module_name1)
        chassis.append_subcomponent(module_name2)
        expected = [
            {"name": "piu1", "state": {"name": "piu1"}},
            {"name": "piu2", "state": {"name": "piu2"}},
        ]
        self.assertEqual(chassis.data["subcomponents"]["subcomponent"], expected)


class TestPlatformComponentTerminalLinePort(unittest.TestCase):
    """Tests for TerminalLinePort."""

    def test_translate_oper_status_ready(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "oper-status": "ready",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(terminal_line_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status_initialize(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "oper-status": "initialize",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(terminal_line_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status_unknown(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "oper-status": "unknown",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(terminal_line_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status_others(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "oper-status": "others",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(terminal_line_port.data["state"]["oper-status"], expected)

    def test_translate_id(self):
        module = {"name": "piu1", "state": {"name": "piu1", "id": 10}}
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "10"
        self.assertEqual(terminal_line_port.data["state"]["id"], expected)

    def test_translate_description(self):
        module = {
            "name": "piu1",
            "state": {"name": "piu1", "description": "CFP2-DCO module information."},
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "CFP2-DCO module information."
        self.assertEqual(terminal_line_port.data["state"]["description"], expected)

    def test_translate_location(self):
        module = {"name": "piu1", "state": {"name": "piu1", "location": "1"}}
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "1"
        self.assertEqual(terminal_line_port.data["state"]["location"], expected)

    def test_translate_admin_status_up(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "admin-status": "up",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "ENABLED"
        self.assertEqual(
            terminal_line_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_admin_status_down(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "admin-status": "down",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "DISABLED"
        self.assertEqual(
            terminal_line_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_admin_status_unknown(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "admin-status": "unknown",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "DISABLED"
        self.assertEqual(
            terminal_line_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_admin_status_others(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "admin-status": "others",
            },
        }
        name = "line-piu1"
        terminal_line_port = TerminalLinePort(name, module)
        terminal_line_port.translate()
        expected = "DISABLED"
        self.assertEqual(
            terminal_line_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_empty(self):
        module = {}
        terminal_line_port = TerminalLinePort("line-piu1", module)
        terminal_line_port.translate()
        expected = {
            "name": "line-piu1",
            "state": {
                "name": "line-piu1",
                "type": "openconfig-platform-types:PORT",
                "removable": False,
            },
            "port": {
                "optical-port": {
                    "state": {
                        "optical-port-type": "openconfig-transport-types:TERMINAL_LINE"
                    }
                }
            },
        }
        self.assertEqual(terminal_line_port.data, expected)

    def test_translate_none(self):
        terminal_line_port = TerminalLinePort("line-piu1", None)
        terminal_line_port.translate()
        expected = {
            "name": "line-piu1",
            "state": {
                "name": "line-piu1",
                "type": "openconfig-platform-types:PORT",
                "removable": False,
            },
            "port": {
                "optical-port": {
                    "state": {
                        "optical-port-type": "openconfig-transport-types:TERMINAL_LINE"
                    }
                }
            },
        }
        self.assertEqual(terminal_line_port.data, expected)

    def test_set_parent(self):
        module = {}
        line_port_name = "line-piu1"
        chassis_name = "CHASSIS"
        terminal_line_port = TerminalLinePort(line_port_name, module)
        terminal_line_port.set_parent(chassis_name)
        expected = "CHASSIS"
        self.assertEqual(terminal_line_port.data["state"]["parent"], expected)

    def test_append_subcomponent(self):
        module = {}
        line_port_name = "line-piu1"
        line_transceiver_name = "transceiver-line-piu1"
        terminal_line_port = TerminalLinePort(line_port_name, module)
        terminal_line_port.append_subcomponent(line_transceiver_name)
        expected = [
            {
                "name": "transceiver-line-piu1",
                "state": {"name": "transceiver-line-piu1"},
            }
        ]
        self.assertEqual(
            terminal_line_port.data["subcomponents"]["subcomponent"], expected
        )


class TestPlatformComponentLineTransceiver(unittest.TestCase):
    """Tests for LineTransceiver."""

    def test_translate_id(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "id": 100,
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "100"
        self.assertEqual(line_transceiver.data["state"]["id"], expected)

    def test_translate_description(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "description": "CFP2-DCO module information.",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "CFP2-DCO module information."
        self.assertEqual(line_transceiver.data["state"]["description"], expected)

    def test_translate_vender_name(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "vendor-name": "Vendor Name",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "Vendor Name"
        self.assertEqual(line_transceiver.data["state"]["mfg-name"], expected)

    def test_translate_firmware_version(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "firmware-version": "Firmware Version",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "Firmware Version"
        self.assertEqual(line_transceiver.data["state"]["software-version"], expected)

    def test_translate_vendor_serial_number(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "vendor-serial-number": "Vendor Serial number",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "Vendor Serial number"
        self.assertEqual(line_transceiver.data["state"]["serial-no"], expected)

    def test_translate_vendor_part_number(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "vendor-part-number": "Vendor Part number",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "Vendor Part number"
        self.assertEqual(line_transceiver.data["state"]["part-no"], expected)

    def test_translate_location(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "location": "1",
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = "1"
        self.assertEqual(line_transceiver.data["state"]["location"], expected)

    def test_translate_temp(self):
        module = {
            "name": "piu1",
            "state": {
                "name": "piu1",
                "temp": 1.3372036854775807,
            },
        }
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = 1.3
        self.assertEqual(
            line_transceiver.data["state"]["temperature"]["instant"], expected
        )

    def test_translate_empty(self):
        module = {}
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, module)
        line_transceiver.translate()
        expected = {
            "name": "transceiver-line-piu1",
            "state": {
                "name": "transceiver-line-piu1",
                "type": "openconfig-platform-types:TRANSCEIVER",
                "removable": True,
            },
        }
        self.assertEqual(line_transceiver.data, expected)

    def test_translate_none(self):
        name = "transceiver-line-piu1"
        line_transceiver = LineTransceiver(name, None)
        line_transceiver.translate()
        expected = {
            "name": "transceiver-line-piu1",
            "state": {
                "name": "transceiver-line-piu1",
                "type": "openconfig-platform-types:TRANSCEIVER",
                "removable": True,
            },
        }
        self.assertEqual(line_transceiver.data, expected)

    def test_set_parent(self):
        module = {}
        line_transceiver_name = "transceiver-line-piu1"
        line_port_name = "line-piu1"
        line_transceiver = LineTransceiver(line_transceiver_name, module)
        line_transceiver.set_parent(line_port_name)
        expected = "line-piu1"
        self.assertEqual(line_transceiver.data["state"]["parent"], expected)

    def test_append_subcomponent(self):
        module = {}
        line_transceiver_name = "transceiver-line-piu1"
        optical_channel_name = "och-transceiver-line-piu1-1"
        line_transceiver = LineTransceiver(line_transceiver_name, module)
        line_transceiver.append_subcomponent(optical_channel_name)
        expected = [
            {
                "name": "och-transceiver-line-piu1-1",
                "state": {"name": "och-transceiver-line-piu1-1"},
            }
        ]
        self.assertEqual(
            line_transceiver.data["subcomponents"]["subcomponent"], expected
        )

    def test_update_by_parent(self):
        module = {"name": "piu1", "state": {"name": "piu1", "oper-status": "ready"}}
        line_port_name = "line-piu1"
        line_transceiver_name = "transceiver-line-piu1"
        terminal_line_port = TerminalLinePort(line_port_name, module)
        line_transceiver = LineTransceiver(line_transceiver_name, module)
        terminal_line_port.translate()
        line_transceiver.update_by_parent(terminal_line_port)
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(line_transceiver.data["state"]["oper-status"], expected)


class TestPlatformComponentOpticalChannel(unittest.TestCase):
    """Tests for OptocalChannel."""

    def test_translate_oper_status_ready(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "ready",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_reset(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "reset",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_initialize(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "initialize",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_low_power(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "low-power",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_high_power_up(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "high-power-up",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_tx_off(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "tx-off",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_chennel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_chennel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_chennel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_tx_turn_on(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "tx-turn-on",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_chennel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_chennel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_chennel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_tx_turn_off(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "tx-turn-off",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_high_power_down(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "high-power-down",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_fault(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "fault",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(optical_channel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_unknown(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "unknown",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_chennel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_chennel.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(optical_chennel.data["state"]["oper-status"], expected)

    def test_translate_oper_status_others(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "oper-status": "others",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_chennel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_chennel.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(optical_chennel.data["state"]["oper-status"], expected)

    def test_translate_id(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {"name": "1", "state": {"name": "1", "id": 100}}
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "100"
        self.assertEqual(optical_channel.data["state"]["id"], expected)

    def test_translate_description(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {"name": "1", "description": "CFP2-DCO module information."},
        }
        name = "och-transceiverline-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "CFP2-DCO module information."
        self.assertEqual(optical_channel.data["state"]["description"], expected)

    def test_translate_index(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {"name": "1", "state": {"name": "1", "index": 1}}
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = "1"
        self.assertEqual(optical_channel.data["state"]["location"], expected)

    def test_translate_tx_laser_freq(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "tx-laser-freq": 100000000,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 100
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["frequency"], expected
        )

    def test_translate_output_power(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "output-power": 3.3372036854775807,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 3.34
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["target-output-power"],
            expected,
        )

    def test_translate_operational_mode_100(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "sc-fec",
                "client-signal-mapping-type": "otu4-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 100
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_operational_mode_101(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "100g",
                "modulation-format": "dp-qpsk",
                "fec-type": "ofec",
                "client-signal-mapping-type": "flexo-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 101
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_operational_mode_200(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "200g",
                "modulation-format": "dp-16-qam",
                "fec-type": "ofec",
                "client-signal-mapping-type": "flexo-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 200
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_operational_mode_201(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "200g",
                "modulation-format": "dp-qpsk",
                "fec-type": "ofec",
                "client-signal-mapping-type": "flexo-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 201
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_operational_mode_300(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "300g",
                "modulation-format": "dp-8-qam",
                "fec-type": "ofec",
                "client-signal-mapping-type": "flexo-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 300
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_operational_mode_400(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "line-rate": "400g",
                "modulation-format": "dp-16-qam",
                "fec-type": "ofec",
                "client-signal-mapping-type": "flexo-lr",
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 400
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["operational-mode"],
            expected,
        )

    def test_translate_current_chromatic_dispersion_in_range(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "current-chromatic-dispersion": 2000,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 2000
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["chromatic-dispersion"][
                "instant"
            ],
            expected,
        )

    def test_translate_current_chromatic_dispersion_out_of_range_max(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "current-chromatic-dispersion": 92233720368547759,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 92233720368547758.07
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["chromatic-dispersion"][
                "instant"
            ],
            expected,
        )

    def test_translate_current_chromatic_dispersion_out_of_range_min(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "current-chromatic-dispersion": -92233720368547758,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = -92233720368547758.08
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["chromatic-dispersion"][
                "instant"
            ],
            expected,
        )

    def test_translate_current_input_power(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "current-input-power": 1.3372036854775807,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 1.34
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["input-power"]["instant"],
            expected,
        )

    def test_translate_current_output_power(self):
        module = {"name": "piu1", "state": {"name": "piu1"}}
        network_interface = {
            "name": "1",
            "state": {
                "name": "1",
                "current-output-power": 2.3372036854775807,
            },
        }
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = 2.34
        self.assertEqual(
            optical_channel.data["optical-channel"]["state"]["output-power"]["instant"],
            expected,
        )

    def test_translate_empty(self):
        module = {}
        network_interface = {}
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(
            name, module, network_interface, operational_modes
        )
        optical_channel.translate()
        expected = {
            "name": "och-transceiver-line-piu1-1",
            "state": {
                "name": "och-transceiver-line-piu1-1",
                "type": "openconfig-transport-types:OPTICAL_CHANNEL",
                "removable": False,
            },
            "properties": {
                "property": [
                    {
                        "name": "CROSS_CONNECTION",
                        "state": {"name": "CROSS_CONNECTION", "value": "PRESET"},
                    },
                    {"name": "latency", "state": {"name": "latency", "value": None}},
                ]
            },
        }
        self.assertEqual(optical_channel.data, expected)

    def test_translate_none(self):
        name = "och-transceiver-line-piu1-1"
        optical_channel = OpticalChannel(name, None, None, None)
        optical_channel.translate()
        expected = {
            "name": "och-transceiver-line-piu1-1",
            "state": {
                "name": "och-transceiver-line-piu1-1",
                "type": "openconfig-transport-types:OPTICAL_CHANNEL",
                "removable": False,
            },
            "properties": {
                "property": [
                    {
                        "name": "CROSS_CONNECTION",
                        "state": {"name": "CROSS_CONNECTION", "value": "PRESET"},
                    },
                    {"name": "latency", "state": {"name": "latency", "value": None}},
                ]
            },
        }
        self.assertEqual(optical_channel.data, expected)

    def test_set_parent(self):
        module = {}
        network_interface = {}
        optical_channel_name = "och-transceiver-line-piu1-1"
        line_tarnsceiver_name = "transceiver-line-piu1"
        optical_channel = OpticalChannel(
            optical_channel_name, module, network_interface, operational_modes
        )
        optical_channel.set_parent(line_tarnsceiver_name)
        expected = "transceiver-line-piu1"
        self.assertEqual(optical_channel.data["state"]["parent"], expected)


class TestPlatformComponentTerminalClientPort(unittest.TestCase):
    """Tests for TerminalClientPort."""

    def test_translate_oper_status1(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
            "transceiver": {"state": {"presence": "PRESENT"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "UP",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(terminal_client_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status2(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
            "transceiver": {"state": {"presence": "PRESENT"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "DOWN",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(terminal_client_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status3(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
            "transceiver": {"state": {"presence": "PRESENT"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "DORMANT",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(terminal_client_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status4(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
            "transceiver": {"state": {"presence": "UNPLUGGED"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "UP",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(terminal_client_port.data["state"]["oper-status"], expected)

    def test_translate_oper_status5(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
            "transceiver": {"state": {"presence": "PRESENT"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "others",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(terminal_client_port.data["state"]["oper-status"], expected)

    def test_translate_id(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
                "id": 200,
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "200"
        self.assertEqual(terminal_client_port.data["state"]["id"], expected)

    def test_translate_description(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
                "description": "QSFP-28 transceiver information.",
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "QSFP-28 transceiver information."
        self.assertEqual(terminal_client_port.data["state"]["description"], expected)

    def test_translate_admin_status_up(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {"name": "Ethernet1/0/1", "admin-status": "UP"},
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "ENABLED"
        self.assertEqual(
            terminal_client_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_admin_status_down(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {"name": "Ethernet1/0/1", "admin-status": "DOWN"},
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "DISABLED"
        self.assertEqual(
            terminal_client_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_admin_status_others(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {"name": "Ethernet1/0/1", "admin-status": "others"},
            "component-connection": {"platform": {"component": "port1"}},
        }
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = "DISABLED"
        self.assertEqual(
            terminal_client_port.data["port"]["optical-port"]["state"]["admin-state"],
            expected,
        )

    def test_translate_empty(self):
        component = {}
        interface = {}
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, component, interface)
        terminal_client_port.translate()
        expected = {
            "name": "client-port1",
            "state": {
                "name": "client-port1",
                "type": "openconfig-platform-types:PORT",
                "removable": False,
            },
            "port": {
                "optical-port": {
                    "state": {
                        "optical-port-type": "openconfig-transport-types:TERMINAL_CLIENT"
                    }
                }
            },
        }
        self.assertEqual(terminal_client_port.data, expected)

    def test_translate_none(self):
        name = "client-port1"
        terminal_client_port = TerminalClientPort(name, None, None)
        terminal_client_port.translate()
        expected = {
            "name": "client-port1",
            "state": {
                "name": "client-port1",
                "type": "openconfig-platform-types:PORT",
                "removable": False,
            },
            "port": {
                "optical-port": {
                    "state": {
                        "optical-port-type": "openconfig-transport-types:TERMINAL_CLIENT"
                    }
                }
            },
        }
        self.assertEqual(terminal_client_port.data, expected)

    def test_set_parent(self):
        component = {}
        interface = {}
        client_port_name = "client-port1"
        chassis_name = "CHASSIS"
        terminal_client_port = TerminalClientPort(
            client_port_name, component, interface
        )
        terminal_client_port.set_parent(chassis_name)
        expected = "CHASSIS"
        self.assertEqual(terminal_client_port.data["state"]["parent"], expected)

    def test_append_subcomponent(self):
        component = {}
        interface = {}
        client_port_name = "client-port1"
        clinet_transceiver_name = "transceiver-client-port1"
        terminal_client_port = TerminalClientPort(
            client_port_name, component, interface
        )
        terminal_client_port.append_subcomponent(clinet_transceiver_name)
        expected = [
            {
                "name": "transceiver-client-port1",
                "state": {"name": "transceiver-client-port1"},
            }
        ]
        self.assertEqual(
            terminal_client_port.data["subcomponents"]["subcomponent"], expected
        )


class TestPlatformComponentClinetTransceiver(unittest.TestCase):
    """Tests for ClientTransceiver."""

    def test_translate_id(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
                "id": 200,
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
        }
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = "200"
        self.assertEqual(transceiver.data["state"]["id"], expected)

    def test_translate_description(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "type": "TRANSCEIVER",
                "description": "QSFP-28 transceiver information.",
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
        }
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = "QSFP-28 transceiver information."
        self.assertEqual(transceiver.data["state"]["description"], expected)

    def test_translate_vendor(self):
        component = {
            "name": "port1",
            "state": {"name": "port1", "type": "TRANSCEIVER"},
            "transceiver": {
                "state": {
                    "vendor": "Vendor Name",
                }
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
        }
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = "Vendor Name"
        self.assertEqual(transceiver.data["state"]["mfg-name"], expected)

    def test_translate_serial(self):
        component = {
            "name": "port1",
            "state": {"name": "port1", "type": "TRANSCEIVER"},
            "transceiver": {
                "state": {
                    "serial": "Serial number",
                }
            },
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
        }
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = "Serial number"
        self.assertEqual(transceiver.data["state"]["serial-no"], expected)

    def test_translate_model(self):
        component = {
            "name": "port1",
            "state": {"name": "port1", "type": "TRANSCEIVER"},
            "transceiver": {"state": {"model": "Model number"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
            },
        }
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = "Model number"
        self.assertEqual(transceiver.data["state"]["part-no"], expected)

    def test_translate_empty(self):
        component = {}
        interface = {}
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, component, interface)
        transceiver.translate()
        expected = {
            "name": "transceiver-client-port1",
            "state": {
                "name": "transceiver-client-port1",
                "type": "openconfig-platform-types:TRANSCEIVER",
                "removable": True,
            },
        }
        self.assertEqual(transceiver.data, expected)

    def test_translate_none(self):
        name = "transceiver-client-port1"
        transceiver = ClientTransceiver(name, None, None)
        transceiver.translate()
        expected = {
            "name": "transceiver-client-port1",
            "state": {
                "name": "transceiver-client-port1",
                "type": "openconfig-platform-types:TRANSCEIVER",
                "removable": True,
            },
        }
        self.assertEqual(transceiver.data, expected)

    def test_set_parent(self):
        component = {}
        interface = {}
        client_transceiver_name = "transceiver-client-port1"
        client_port_name = "client-port1"
        transceiver = ClientTransceiver(client_transceiver_name, component, interface)
        transceiver.set_parent(client_port_name)
        expected = "client-port1"
        self.assertEqual(transceiver.data["state"]["parent"], expected)

    def test_update_by_parent(self):
        component = {
            "name": "port1",
            "state": {
                "name": "port1",
                "id": 200,
                "description": "QSFP-28 transceiver information.",
            },
            "transceiver": {"state": {"presence": "PRESENT"}},
        }
        interface = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "oper-status": "UP",
                "admin-status": "UP",
            },
        }
        client_name = "client-port1"
        transceiver_name = "transceiver-client-port1"
        transceiver = ClientTransceiver(client_name, component, interface)
        terminal_client_port = TerminalClientPort(
            transceiver_name, component, interface
        )
        terminal_client_port.translate()
        transceiver.update_by_parent(terminal_client_port)
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(transceiver.data["state"]["oper-status"], expected)


class TestPlatformComponentFan(unittest.TestCase):
    """Tests for Fan."""

    def test_translate_oper_status1(self):
        component = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "FAN",
            },
            "fan": {"state": {"fan-state": "PRESENT", "status": "RUNNING"}},
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(fan.data["state"]["oper-status"], expected)

    def test_translate_oper_status2(self):
        component = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "FAN",
            },
            "fan": {"state": {"fan-state": "PRESENT", "status": "FAILED"}},
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(fan.data["state"]["oper-status"], expected)

    def test_translate_oper_status3(self):
        component = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "FAN",
            },
            "fan": {"state": {"fan-state": "NOT-PRESENT", "status": "RUNNING"}},
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(fan.data["state"]["oper-status"], expected)

    def test_translate_oper_status4(self):
        component = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "FAN",
            },
            "fan": {"state": {"fan-state": "others", "status": "RUNNING"}},
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(fan.data["state"]["oper-status"], expected)

    def test_translate_id(self):
        component = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "FAN",
                "id": 300,
            },
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "300"
        self.assertEqual(fan.data["state"]["id"], expected)

    def test_translate_description(self):
        component = {
            "name": "fan",
            "state": {"name": "fan", "type": "FAN", "description": "Fan information."},
        }
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = "Fan information."
        self.assertEqual(fan.data["state"]["description"], expected)

    def test_translate_empty(self):
        component = {}
        name = "fan"
        fan = Fan(name, component)
        fan.translate()
        expected = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "openconfig-platform-types:FAN",
            },
        }
        self.assertEqual(fan.data, expected)

    def test_translate_none(self):
        name = "fan"
        fan = Fan(name, None)
        fan.translate()
        expected = {
            "name": "fan",
            "state": {
                "name": "fan",
                "type": "openconfig-platform-types:FAN",
            },
        }
        self.assertEqual(fan.data, expected)

    def test_set_parent(self):
        component = {}
        fan_name = "fan"
        chassis_name = "CHASSIS"
        fan = Fan(fan_name, component)
        fan.set_parent(chassis_name)
        expected = "CHASSIS"
        self.assertEqual(fan.data["state"]["parent"], expected)


class TestPlatformComponentPowerSupply(unittest.TestCase):
    """Tests for PowerSupply."""

    def test_translate_oper_status1(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "psu-state": "PRESENT",
                    "status": "RUNNING",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "openconfig-platform-types:ACTIVE"
        self.assertEqual(power_supply.data["state"]["oper-status"], expected)

    def test_translate_oper_status2(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "psu-state": "PRESENT",
                    "status": "UNPLUGGED-OR-FAILED",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "openconfig-platform-types:INACTIVE"
        self.assertEqual(power_supply.data["state"]["oper-status"], expected)

    def test_translate_oper_status3(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "psu-state": "NOT-PRESENT",
                    "status": "RUNNING",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(power_supply.data["state"]["oper-status"], expected)

    def test_translate_oper_status4(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "psu-state": "others",
                    "status": "RUNNING",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "openconfig-platform-types:DISABLED"
        self.assertEqual(power_supply.data["state"]["oper-status"], expected)

    def test_translate_id(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
                "id": 400,
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "400"
        self.assertEqual(power_supply.data["state"]["id"], expected)

    def test_translate_description(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
                "description": "PSU information.",
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "PSU information."
        self.assertEqual(power_supply.data["state"]["description"], expected)

    def test_translate_serial(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "serial": "Serial number",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "Serial number"
        self.assertEqual(power_supply.data["state"]["serial-no"], expected)

    def test_translate_model(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "model": "Model number",
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = "Model number"
        self.assertEqual(power_supply.data["state"]["part-no"], expected)

    def test_translate_output_power_in_range(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "output-power": 50000,
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = 50
        self.assertEqual(power_supply.data["state"]["used-power"], expected)

    def test_translate_output_power_out_of_range(self):
        component = {
            "name": "power supply",
            "state": {
                "name": "power supply",
                "type": "PSU",
            },
            "psu": {
                "state": {
                    "output-power": -50000,
                }
            },
        }
        name = "power supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = 0
        self.assertEqual(power_supply.data["state"]["used-power"], expected)

    def test_translate_empty(self):
        component = {}
        name = "power-supply"
        power_supply = PowerSupply(name, component)
        power_supply.translate()
        expected = {
            "name": "power-supply",
            "state": {
                "name": "power-supply",
                "type": "openconfig-platform-types:POWER_SUPPLY",
            },
        }
        self.assertEqual(power_supply.data, expected)

    def test_translate_none(self):
        name = "power-supply"
        power_supply = PowerSupply(name, None)
        power_supply.translate()
        expected = {
            "name": "power-supply",
            "state": {
                "name": "power-supply",
                "type": "openconfig-platform-types:POWER_SUPPLY",
            },
        }
        self.assertEqual(power_supply.data, expected)

    def test_set_parent(self):
        component = {}
        power_supply_name = "power-supply"
        chassis_name = "CHASSIS"
        power_supply = PowerSupply(power_supply_name, component)
        power_supply.set_parent(chassis_name)
        expected = "CHASSIS"
        self.assertEqual(power_supply.data["state"]["parent"], expected)


class TestPlatformComponentFactory(unittest.TestCase):
    """Tests for ComponentFactory."""

    def test_create(self):
        gs_components = [
            {
                "name": "SYS",
                "state": {
                    "name": "SYS",
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
                "state": {"name": "THERMAL SENSOR1", "type": "THERMAL"},
                "thermal": {"state": {"temperature": 10000}},
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
        gs_modules = [
            {
                "name": "piu1",
                "state": {
                    "name": "piu1",
                    "type": "PORT",
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
            }
        ]
        gs_interfaces = [
            {
                "name": "Ethernet1/0/1",
                "state": {
                    "name": "Ethernet1/0/1",
                    "oper-status": "UP",
                    "admin-status": "UP",
                },
                "component-connection": {"platform": {"component": "port1"}},
            }
        ]
        gs_system = {"state": {"software-version": "Software version"}}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "system": gs_system,
        }
        component_name_resolver = ComponentNameResolver()
        component_factory = ComponentFactory(operational_modes, component_name_resolver)
        components = component_factory.create(gs)
        expected = [
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
                        {"name": "line-piu1", "state": {"name": "line-piu1"}},
                        {"name": "client-port1", "state": {"name": "client-port1"}},
                        {"name": "fan", "state": {"name": "fan"}},
                        {"name": "power supply", "state": {"name": "power supply"}},
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
                    "temperature": {
                        "instant": 1.3,
                    },
                    "removable": True,
                },
                "subcomponents": {
                    "subcomponent": [
                        {
                            "name": "och-transceiver-line-piu1-1",
                            "state": {"name": "och-transceiver-line-piu1-1"},
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
                        "chromatic-dispersion": {"instant": 2000},
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
                            "state": {"name": "CROSS_CONNECTION", "value": "PRESET"},
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
        self.assertEqual(components, expected)

    def test_create_no_component_connection(self):
        gs_components = [
            {
                "name": "SYS",
                "state": {
                    "name": "SYS",
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
                "state": {"name": "THERMAL SENSOR1", "type": "THERMAL"},
                "thermal": {"state": {"temperature": 10000}},
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
        ]
        gs_modules = []
        gs_interfaces = [
            {
                "name": "Ethernet1/0/1",
                "state": {
                    "name": "Ethernet1/0/1",
                    "oper-status": "UP",
                    "admin-status": "UP",
                },
            }
        ]
        gs_system = {"state": {"software-version": "Software version"}}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "system": gs_system,
        }
        component_name_resolver = ComponentNameResolver()
        component_factory = ComponentFactory(operational_modes, component_name_resolver)
        components = component_factory.create(gs)
        expected = [
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
                        {"name": "client-port1", "state": {"name": "client-port1"}},
                    ]
                },
            },
            {
                "name": "client-port1",
                "state": {
                    "name": "client-port1",
                    "type": "openconfig-platform-types:PORT",
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
                            "optical-port-type": "openconfig-transport-types:TERMINAL_CLIENT"
                        }
                    }
                },
            },
            {
                "name": "transceiver-client-port1",
                "state": {
                    "name": "transceiver-client-port1",
                    "type": "openconfig-platform-types:TRANSCEIVER",
                    "id": "200",
                    "description": "QSFP-28 transceiver information.",
                    "mfg-name": "Vendor Name",
                    "serial-no": "Serial number",
                    "part-no": "Model number",
                    "parent": "client-port1",
                    "removable": True,
                },
            },
        ]
        self.assertEqual(components, expected)

    def test_create_twice(self):
        gs_components = [
            {
                "name": "SYS",
                "state": {
                    "name": "SYS",
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
                "state": {"name": "THERMAL SENSOR1", "type": "THERMAL"},
                "thermal": {"state": {"temperature": 10000}},
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
        gs_modules = [
            {
                "name": "piu1",
                "state": {
                    "name": "piu1",
                    "type": "PORT",
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
            }
        ]
        gs_interfaces = [
            {
                "name": "Ethernet1/0/1",
                "state": {
                    "name": "Ethernet1/0/1",
                    "oper-status": "UP",
                    "admin-status": "UP",
                },
                "component-connection": {"platform": {"component": "port1"}},
            }
        ]
        gs_system = {"state": {"software-version": "Software version"}}
        gs = {
            "components": gs_components,
            "modules": gs_modules,
            "interfaces": gs_interfaces,
            "system": gs_system,
        }
        component_name_resolver = ComponentNameResolver()
        component_factory = ComponentFactory(operational_modes, component_name_resolver)
        components = component_factory.create(gs)
        expected = [
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
                        {"name": "line-piu1", "state": {"name": "line-piu1"}},
                        {"name": "client-port1", "state": {"name": "client-port1"}},
                        {"name": "fan", "state": {"name": "fan"}},
                        {"name": "power supply", "state": {"name": "power supply"}},
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
                    "temperature": {
                        "instant": 1.3,
                    },
                    "removable": True,
                },
                "subcomponents": {
                    "subcomponent": [
                        {
                            "name": "och-transceiver-line-piu1-1",
                            "state": {"name": "och-transceiver-line-piu1-1"},
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
                        "chromatic-dispersion": {"instant": 2000},
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
                            "state": {"name": "CROSS_CONNECTION", "value": "PRESET"},
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
        self.assertEqual(components, expected)
        components = component_factory.create(gs)
        self.assertEqual(components, expected)


class TestPlatformPortAdminStateHandlerTerminalLine(unittest.TestCase):
    """Tests for PortAdminStateHandler (TERMINAL_LINE)."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("goldstone-gearbox")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }

    def tearDown(self):
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()

    # Test for terminal line port.
    def test_set_terminal_line_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "up")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_terminal_line_module_configured(self):
        # Target module has been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "up")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_set_terminal_line_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status",
            "down",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "down")
        self.assertFalse(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "up")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "down")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_delete_terminal_line_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_terminal_line_module_configured(self):
        # Target module has been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_delete_terminal_line_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status",
            "down",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='line-piu1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "down")
        self.assertFalse(handler.module_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "down")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)


class TestPlatformPortAdminStateHandlerTerminalClient(unittest.TestCase):
    """Tests for PortAdminStateHandler (TERMINAL_CLIENT)."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("goldstone-gearbox")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }
        mock_servers = {
            "goldstone-interfaces": {
                "interfaces": {
                    "interface": [
                        {
                            "name": "Ethernet1/0/1",
                            "state": {
                                "name": "Ethernet1/0/1",
                            },
                            "component-connection": {
                                "platform": {"component": "port1"}
                            },
                        },
                    ]
                }
            },
            "goldstone-gearbox": {
                "gearboxes": {
                    "gearbox": [
                        {
                            "name": "1",
                            "connections": {
                                "connection": [
                                    {
                                        "client-interface": "Ethernet1/0/1",
                                        "line-interface": "Ethernet1/1/1",
                                    },
                                ]
                            },
                        },
                    ]
                }
            },
        }
        self.run_mock_servers(mock_servers)

    def tearDown(self):
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()
        self.join_mock_servers()

    def run_mock_servers(self, mock_servers):
        self.q = Queue()
        self.process = Process(
            target=run_mock_server, args=(self.q, mock_servers.keys())
        )
        self.process.start()
        time.sleep(1)
        for server, data in mock_servers.items():
            self.q.put(
                {
                    "type": "set-oper-data",
                    "server": server,
                    "data": data,
                }
            )
        time.sleep(1)

    def join_mock_servers(self):
        self.q.put({"type": "stop"})
        self.process.join()

    def test_set_terminal_client_interface_not_configured(self):
        # Target interface has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.hostif_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/1/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_terminal_client_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name",
            "Ethernet1/1/1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.hostif_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/1/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name"
        self.conn.get(xpath)

    def test_set_terminal_client_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "DOWN",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name",
            "Ethernet1/1/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status",
            "DOWN",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        value = "ENABLED"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, ("DOWN", "DOWN"))
        self.assertFalse(handler.hostif_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/1/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "DOWN")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "DOWN")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name"
        self.conn.get(xpath)

    def test_delete_terminal_client_interface_not_configured(self):
        # Target interface has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.hostif_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_terminal_client_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name",
            "Ethernet1/1/1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.hostif_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name"
        self.conn.get(xpath)

    def test_delete_terminal_client_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "UP",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/name",
            "Ethernet1/1/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status",
            "UP",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='client-port1']/port/"
            "openconfig-transport-line-common:optical-port/config/admin-state"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = PortAdminStateHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, ("UP", "UP"))
        self.assertFalse(handler.hostif_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/1/1']/name"
        self.conn.get(xpath)


class TestPlatformOpticalChannelFrequencyHandler(unittest.TestCase):
    """Tests for OpticalChannelFrequencyHandler."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }

    def tearDown(self):
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()

    def test_set_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        value = 100
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100000000)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        value = 100
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100000000)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_set_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        value = 100
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100000000)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_set_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq",
            10,
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        value = 100
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, 10)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100000000)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 10)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_module_not_configured(self):
        # Target module has not been configured.

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_delete_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq",
            10,
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/frequency"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelFrequencyHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, 10)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/tx-laser-freq",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/tx-laser-freq"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 10)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)


class TestPlatformOpticalChannelTargetOutputPowerHandler(unittest.TestCase):
    """Tests for OPpticalChannelTargetOutputPowerHandler."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }

    def tearDown(self):
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()

    def test_set_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        value = 100.0
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100.0)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        value = 100.0
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100.0)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_set_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        value = 100.0
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100.0)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_set_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power",
            10.0,
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        value = 100.0
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, 10.0)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 100.0)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 10.0)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_delete_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_item_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power",
            10.0,
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/target-output-power"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelTargetOutputPowerHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, 10.0)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/output-power",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/output-power"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, 10.0)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)


class TestPlatformOpticalChannelOperationalModeHandler(unittest.TestCase):
    """Tests for OPpticalChannelOperationalModeHandler."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-transponder")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }

    def tearDown(self):
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()

    def test_set_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        value = 200
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "200g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-16-qam")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "ofec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "flexo-lr")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        value = 200
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertTrue(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "200g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-16-qam")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "ofec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "flexo-lr")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_set_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        value = 200
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "200g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-16-qam")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "ofec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "flexo-lr")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_set_items_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate",
            "100g",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format",
            "dp-qpsk",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type",
            "sc-fec",
        )
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # self.conn.set(
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type",
        #     "otu4-lr",
        # )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        value = 200
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(
            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # handler.original_value, ("100g", "dp-qpsk", "sc-fec", "otu4-lr")
            handler.original_value,
            ("100g", "dp-qpsk", "sc-fec", None),
        )
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-transponder:modules/module[name='piu1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "piu1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "1")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "200g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-16-qam")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "ofec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "flexo-lr")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "100g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-qpsk")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "sc-fec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "otu4-lr")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_module_not_configured(self):
        # Target module has not been configured.
        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
            "/goldstone-transponder:modules/module[name='piu1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_module_configured(self):
        # Target module has been configured, netif has not been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)

    def test_delete_netif_configured(self):
        # Target module and netif have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)

    def test_delete_items_configured(self):
        # Target items have been configured.
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/config/name",
            "piu1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/name",
            "1",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate",
            "100g",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format",
            "dp-qpsk",
        )
        self.conn.set(
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type",
            "sc-fec",
        )
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # self.conn.set(
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type",
        #     "otu4-lr",
        # )
        self.conn.apply()

        server = PlatformServer(self.conn, operational_modes)
        xpath = (
            "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']/"
            "openconfig-terminal-device:optical-channel/config/operational-mode"
        )
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "operational-modes": operational_modes,
            "cnr": ComponentNameResolver(),
            "sess": self.sess,
        }
        handler = OpticalChannelOperationalModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(
            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # handler.original_value, ("100g", "dp-qpsk", "sc-fec", "otu4-lr")
            handler.original_value,
            ("100g", "dp-qpsk", "sc-fec", None),
        )
        self.assertFalse(handler.module_created)
        self.assertFalse(handler.netif_created)

        handler.apply(user)
        self.sess["running"].apply()
        deleted = [
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/line-rate",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/modulation-format",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/fec-type",
            "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/config/"
            "client-signal-mapping-type",
        ]
        for xpath in deleted:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/line-rate"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "100g")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/modulation-format"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "dp-qpsk")
        xpath = (
            "/goldstone-transponder:modules/module[name='piu1']/"
            "network-interface[name='1']/config/fec-type"
        )
        data = self.conn.get(xpath)
        self.assertEqual(data, "sc-fec")
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # xpath = (
        #     "/goldstone-transponder:modules/module[name='piu1']/"
        #     "network-interface[name='1']/config/client-signal-mapping-type"
        # )
        # data = self.conn.get(xpath)
        # self.assertEqual(data, "otu4-lr")
        xpath = "/goldstone-transponder:modules/module[name='piu1']/name"
        self.conn.get(xpath)
        xpath = "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='1']/name"
        self.conn.get(xpath)


class TestPlatformServer(XlateTestCase):
    """Tests for PlatformServer.

    Notes:
        - Mock servers take less than a second to complete the preparation. All test methods should wait a second after
          calling set_mock_oper_data() to start test.
        - Some test methods contain several tests instead of one test. It is to reduce the time to test. All test
          methods take over a second for each because of the time to wait mock servers.
    """

    XLATE_SERVER = PlatformServer
    XLATE_SERVER_OPT = [operational_modes]
    XLATE_MODULES = ["openconfig-platform"]
    MOCK_MODULES = [
        "goldstone-interfaces",
        "goldstone-gearbox",
        "goldstone-platform",
        "goldstone-transponder",
        "goldstone-system",
    ]

    async def test_get_chassis(self):
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
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
        mock_data_system = {
            "system": {"state": {"software-version": "Software version"}}
        }
        self.set_mock_oper_data("goldstone-system", mock_data_system)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='CHASSIS']",
                strip=False,
            )
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
                        }
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_terminal_line_port(self):
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
                            "location": "1",
                            "admin-status": "up",
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='line-piu1']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
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
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_line_transceiver(self):
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
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='transceiver-line-piu1']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
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
                        }
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_optical_channel(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "oper-status": "ready",
                                    "id": 1000,
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
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='och-transceiver-line-piu1-1']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
                        {
                            "name": "och-transceiver-line-piu1-1",
                            "state": {
                                "name": "och-transceiver-line-piu1-1",
                                "type": "openconfig-transport-types:OPTICAL_CHANNEL",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "1000",
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
                                        "state": {"name": "latency", "value": ""},
                                    },
                                ]
                            },
                        }
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_terminal_client_port(self):
        mock_data_platform = {
            "components": {
                "component": [
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
                            }
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
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
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interface)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='client-port1']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
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
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_client_transceiver(self):
        mock_data_platform = {
            "components": {
                "component": [
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
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)
        mock_data_interface = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {
                            "name": "Ethernet1/0/1",
                            "oper-status": "UP",
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interface)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='transceiver-client-port1']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
                        {
                            "name": "transceiver-client-port1",
                            "state": {
                                "name": "transceiver-client-port1",
                                "type": "openconfig-platform-types:TRANSCEIVER",
                                "oper-status": "openconfig-platform-types:ACTIVE",
                                "id": "200",
                                "description": "QSFP-28 transceiver information.",
                                "parent": "client-port1",
                                "mfg-name": "Vendor Name",
                                "serial-no": "Serial number",
                                "part-no": "Model number",
                                "removable": True,
                            },
                        },
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_fan(self):
        mock_data_platform = {
            "components": {
                "component": [
                    {
                        "name": "fan",
                        "state": {
                            "name": "fan",
                            "type": "FAN",
                            "id": 300,
                            "description": "Fan information.",
                        },
                        "fan": {"state": {"fan-state": "PRESENT", "status": "RUNNING"}},
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='fan']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
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
                        }
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_power_supply(self):
        mock_data_platform = {
            "components": {
                "component": [
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
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components/component[name='power supply']",
                strip=False,
            )
            expected = {
                "components": {
                    "component": [
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
                        }
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_get_all(self):
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
                    }
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
                    }
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            data = self.conn.get_operational(
                "/openconfig-platform:components", strip=False
            )
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
                                        "state": {"name": "latency", "value": ""},
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

    async def test_set_port_admin_state(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {"name": "piu1", "admin-status": "up"},
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)
        mock_data_interface = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {
                            "name": "Ethernet1/0/1",
                            "admin-status": "UP",
                            "oper-status": "UP",
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    },
                    {
                        "name": "Ethernet1/1/1",
                        "state": {
                            "name": "Ethernet1/1/1",
                            "admin-status": "UP",
                            "oper-status": "UP",
                        },
                        "component-connection": {"platform": {"component": "port1"}},
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-interfaces", mock_data_interface)
        mock_data_gearbox = {
            "gearboxes": {
                "gearbox": [
                    {
                        "name": "1",
                        "connections": {
                            "connection": [
                                {
                                    "client-interface": "Ethernet1/0/1",
                                    "line-interface": "Ethernet1/1/1",
                                },
                            ]
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-gearbox", mock_data_gearbox)
        mock_data_platform = {
            "components": {
                "component": [
                    {
                        "name": "port1",
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            # Set terminal line port ENABLED.
            name = "piu1"
            openconfig_name = "line-piu1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "ENABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "up")

            # Set terminal line port DISABLED.
            name = "piu1"
            openconfig_name = "line-piu1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "DISABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "down")

            # Set terminal line port MAINT.
            name = "piu1"
            openconfig_name = "line-piu1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "MAINT",
            )
            self.conn.apply()

            xpath = f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "down")

            # Delete terminal line port.
            name = "piu1"
            openconfig_name = "line-piu1"
            self.conn.delete(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
            )
            self.conn.apply()

            xpath = f"/goldstone-transponder:modules/module[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

            # Set terminal client port ENABLED.
            hostif_name = "Ethernet1/0/1"
            netif_name = "Ethernet1/1/1"
            openconfig_name = "client-port1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "ENABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{hostif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "UP")
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{netif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "UP")

            # Set terminal client port DISABLED.
            hostif_name = "Ethernet1/0/1"
            netif_name = "Ethernet1/1/1"
            openconfig_name = "client-port1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "DISABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{hostif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "DOWN")
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{netif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "DOWN")

            # Set terminal client port MAINT.
            hostif_name = "Ethernet1/0/1"
            netif_name = "Ethernet1/1/1"
            openconfig_name = "client-port1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
                "MAINT",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{hostif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "DOWN")
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{netif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "DOWN")

            # Delete terminal client port.
            hostif_name = "Ethernet1/0/1"
            netif_name = "Ethernet1/1/1"
            openconfig_name = "client-port1"
            self.conn.delete(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/port/"
                "openconfig-transport-line-common:optical-port/config/admin-state",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{hostif_name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_set_optical_channel_frequency(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {"name": "1", "state": {"name": "1", "tx-laser-freq": 10}}
                        ],
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            # Set.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/frequency",
                10,
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/tx-laser-freq"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10000000)

            # Delete.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.delete(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/frequency",
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/tx-laser-freq"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_set_optical_channel_target_output_power(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {"name": "1", "state": {"name": "1", "output-power": 10}}
                        ],
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            # Set.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/target-output-power",
                10.0,
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/output-power"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10)

            # Delete.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.delete(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/target-output-power"
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/output-power"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_set_optical_channel_operational_mode(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "sc-fec",
                                    "client-signal-mapping-type": "otu4-lr",
                                },
                            }
                        ],
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            # Set 100.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
                100,
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/line-rate"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "100g")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/modulation-format"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "dp-qpsk")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/fec-type"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "sc-fec")

            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # xpath = (
            #     f"/goldstone-transponder:modules/module[name='{module_name}']/"
            #     f"network-interface[name='{netif_name}']/config/client-signal-mapping-type"
            # )
            # data = self.conn.get(xpath)
            # self.assertEqual(data, "otu4-lr")

            # Set 400.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
                400,
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/line-rate"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "400g")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/modulation-format"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "dp-16-qam")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/fec-type"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "ofec")

            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # xpath = (
            #     f"/goldstone-transponder:modules/module[name='{module_name}']/"
            #     f"network-interface[name='{netif_name}']/config/client-signal-mapping-type"
            # )
            # data = self.conn.get(xpath)
            # self.assertEqual(data, "flexo-lr")

            # Delete.
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.delete(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
            )
            self.conn.apply()

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/line-rate"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/modulation-format"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/fec-type"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # xpath = (
            #     f"/goldstone-transponder:modules/module[name='{module_name}']/"
            #     f"network-interface[name='{netif_name}']/config/client-signal-mapping-type"
            # )
            # data = self.conn.get(xpath)
            # self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_set_revert_create(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {
                                "name": "1",
                                "state": {
                                    "name": "1",
                                    "line-rate": "100g",
                                    "modulation-format": "dp-qpsk",
                                    "fec-type": "sc-fec",
                                    "client-signal-mapping-type": "otu4-lr",
                                },
                            }
                        ],
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/frequency",
                10,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/target-output-power",
                10.0,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
                100,
            )
            self.set_mock_change_handler(
                "goldstone-transponder",
                "/modules/module/network-interface/config/fec-type",
                FailApplyChangeHandler,
            )
            time.sleep(1)
            with self.assertRaises(Error):
                self.conn.apply()

            # Check not found.
            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, None)
            xpath = f"/goldstone-transponder:modules/module[name='{module_name}']"
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_set_revert_modify(self):
        mock_data_transponder = {
            "modules": {
                "module": [
                    {
                        "name": "piu1",
                        "state": {
                            "name": "piu1",
                        },
                        "network-interface": [
                            {"name": "1", "state": {"name": "1", "tx-laser-freq": 10}}
                        ],
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-transponder", mock_data_transponder)

        def test():
            module_name = "piu1"
            netif_name = "1"
            openconfig_name = "och-transceiver-line-piu1-1"

            # Set initial configuration.
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/config/name",
                openconfig_name,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/frequency",
                10,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/target-output-power",
                10.0,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
                100,
            )
            self.conn.apply()

            # Check configured values.
            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/tx-laser-freq"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10000000)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/output-power"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10.0)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/line-rate"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "100g")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/modulation-format"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "dp-qpsk")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/fec-type"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "sc-fec")

            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # xpath = (
            #     f"/goldstone-transponder:modules/module[name='{module_name}']/"
            #     f"network-interface[name='{netif_name}']/config/client-signal-mapping-type"
            # )
            # data = self.conn.get(xpath)
            # self.assertEqual(data, "otu4-lr")

            # Update configuration.
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/frequency",
                100,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/target-output-power",
                100.0,
            )
            self.conn.set(
                f"/openconfig-platform:components/component[name='{openconfig_name}']/"
                "openconfig-terminal-device:optical-channel/config/operational-mode",
                200,
            )
            # But failed.
            self.set_mock_change_handler(
                "goldstone-transponder",
                "/modules/module/network-interface/config/fec-type",
                FailApplyChangeHandler,
            )
            time.sleep(1)
            with self.assertRaises(Error):
                self.conn.apply()

            # Check values has not been changed. (Updates are discarded.)
            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/tx-laser-freq"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10000000)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/output-power"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, 10.0)

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/line-rate"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "100g")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/modulation-format"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "dp-qpsk")

            xpath = (
                f"/goldstone-transponder:modules/module[name='{module_name}']/"
                f"network-interface[name='{netif_name}']/config/fec-type"
            )
            data = self.conn.get(xpath)
            self.assertEqual(data, "sc-fec")

            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # xpath = (
            #     f"/goldstone-transponder:modules/module[name='{module_name}']/"
            #     f"network-interface[name='{netif_name}']/config/client-signal-mapping-type"
            # )
            # data = self.conn.get(xpath)
            # self.assertEqual(data, "otu4-lr")

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
