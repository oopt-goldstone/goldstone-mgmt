"""Tests of OpenConfig translater for openconfig-interfaces."""


import unittest
import time
import sysrepo
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector.sysrepo import Change
from goldstone.xlate.openconfig.interfaces import (
    InterfaceServer,
    EthernetCSMACD,
    EnabledHandler,
    FECModeHandler,
)
from tests.lib import XlateTestCase


class TestEthernetCSMACD(unittest.TestCase):
    """Tests for EthernetCSMACD."""

    def test_translate_mtu(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
            "ethernet": {
                "state": {
                    "mtu": 10000,
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = 10000
        self.assertEqual(ethernet_interface.data["state"]["mtu"], expected)

    def test_translate_description(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "description": "Ethernet interface.",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "Ethernet interface."
        self.assertEqual(ethernet_interface.data["state"]["description"], expected)

    def test_translate_admin_status_up(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "admin-status": "UP",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected_admin_status = "UP"
        self.assertEqual(
            ethernet_interface.data["state"]["admin-status"], expected_admin_status
        )
        expected_enabled = True
        self.assertEqual(ethernet_interface.data["state"]["enabled"], expected_enabled)

    def test_translate_admin_status_down(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "admin-status": "DOWN",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected_admin_status = "DOWN"
        self.assertEqual(
            ethernet_interface.data["state"]["admin-status"], expected_admin_status
        )
        expected_enabled = False
        self.assertEqual(ethernet_interface.data["state"]["enabled"], expected_enabled)

    def test_translate_admin_status_not_supported(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "admin-status": "Something",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected_admin_status = "DOWN"
        self.assertEqual(
            ethernet_interface.data["state"]["admin-status"], expected_admin_status
        )
        expected_enabled = False
        self.assertEqual(ethernet_interface.data["state"]["enabled"], expected_enabled)

    def test_translate_oper_status_up(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "oper-status": "UP",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "UP"
        self.assertEqual(ethernet_interface.data["state"]["oper-status"], expected)

    def test_translate_oper_status_down(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "oper-status": "DOWN",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "DOWN"
        self.assertEqual(ethernet_interface.data["state"]["oper-status"], expected)

    def test_translate_oper_status_dormant(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "oper-status": "DORMANT",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "DORMANT"
        self.assertEqual(ethernet_interface.data["state"]["oper-status"], expected)

    def test_translate_oper_status_not_supported(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "oper-status": "Something",
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "UNKNOWN"
        self.assertEqual(ethernet_interface.data["state"]["oper-status"], expected)

    def test_translate_counters(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
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
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = {
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
        }
        self.assertEqual(ethernet_interface.data["state"]["counters"], expected)

    def test_translate_in_pkts_carry_over(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "counters": {
                    "in-unicast-pkts": 100,
                    "in-broadcast-pkts": 200,
                    "in-multicast-pkts": 300,
                    "in-discards": 400,
                    "in-errors": 500,
                    "in-unknown-protos": 18446744073709551616,
                },
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = 1500
        self.assertEqual(
            ethernet_interface.data["state"]["counters"]["in-pkts"], expected
        )

    def test_translate_out_pkts_carry_over(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
                "counters": {
                    "out-unicast-pkts": 100,
                    "out-broadcast-pkts": 200,
                    "out-multicast-pkts": 300,
                    "out-discards": 400,
                    "out-errors": 18446744073709551616,
                },
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = 1000
        self.assertEqual(
            ethernet_interface.data["state"]["counters"]["out-pkts"], expected
        )

    def test_translate_fec_fc(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
            "ethernet": {
                "state": {
                    "fec": "FC",
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "FEC_FC"
        self.assertEqual(
            ethernet_interface.data["ethernet"]["state"]["fec-mode"], expected
        )

    def test_translate_fec_rc(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
            "ethernet": {
                "state": {
                    "fec": "RS",
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "FEC_RS528"
        self.assertEqual(
            ethernet_interface.data["ethernet"]["state"]["fec-mode"], expected
        )

    def test_translate_fec_none(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
            "ethernet": {
                "state": {
                    "fec": "NONE",
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "FEC_DISABLED"
        self.assertEqual(
            ethernet_interface.data["ethernet"]["state"]["fec-mode"], expected
        )

    def test_translate_fec_not_supported(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
            "ethernet": {
                "state": {
                    "fec": "Something",
                }
            },
        }
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = "FEC_DISABLED"
        self.assertEqual(
            ethernet_interface.data["ethernet"]["state"]["fec-mode"], expected
        )

    def test_translate_hardware_port(self):
        name = "Ethernet1/0/1"
        interface = {
            "name": name,
            "state": {
                "name": name,
            },
        }
        ethernet_interface = EthernetCSMACD(name, "client-port1", interface)
        ethernet_interface.translate()
        expected = "client-port1"
        self.assertEqual(ethernet_interface.data["state"]["hardware-port"], expected)

    def test_translate_empty(self):
        interface = {}
        name = "Ethernet1/0/1"
        ethernet_interface = EthernetCSMACD(name, None, interface)
        ethernet_interface.translate()
        expected = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "type": "iana-if-type:ethernetCsmacd",
            },
        }
        self.assertEqual(ethernet_interface.data, expected)

    def test_translate_none(self):
        name = "Ethernet1/0/1"
        ethernet_interface = EthernetCSMACD(name, None, None)
        ethernet_interface.translate()
        expected = {
            "name": "Ethernet1/0/1",
            "state": {
                "name": "Ethernet1/0/1",
                "type": "iana-if-type:ethernetCsmacd",
            },
        }
        self.assertEqual(ethernet_interface.data, expected)


class TestInterfaceEnabledHandler(unittest.TestCase):
    """Tests for EnabledHandler."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-interfaces")
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

    def test_set_interface_not_configured(self):
        # Target interface has not been configured.
        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        value = True
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        value = True
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)

    def test_set_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "DOWN",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        value = True
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "DOWN")
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "DOWN")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)

    def test_delete_interface_not_configured(self):
        # Target interface has not been configured.
        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)

    def test_delete_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status",
            "UP",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/enabled"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = EnabledHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "UP")
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/admin-status"
        data = self.conn.get(xpath)
        self.assertEqual(data, "UP")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)


class TestInterfaceFECModeHandler(unittest.TestCase):
    """Tests for FECModeHandler."""

    def setUp(self):
        self.conn = Connector()
        self.conn.delete_all("goldstone-interfaces")
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

    def test_set_interface_not_configured(self):
        # Target interface has not been configured.
        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        value = "FEC_FC"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertTrue(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, "FC")

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_set_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        value = "FEC_FC"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, "FC")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)

    def test_set_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec",
            "RS",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        value = "FEC_FC"
        change = Change(sysrepo.ChangeCreated(xpath, value))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "RS")
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name"
        data = self.conn.get(xpath)
        self.assertEqual(data, "Ethernet1/0/1")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, "FC")

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, "RS")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        data = self.conn.get(xpath)

    def test_delete_interface_not_configured(self):
        # Target interface has not been configured.
        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        not_exist = [
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec",
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name",
        ]
        for xpath in not_exist:
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

    def test_delete_interface_configured(self):
        # Target interface has been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, None)
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)

    def test_delete_item_configured(self):
        # Target item have been configured.
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/config/name",
            "Ethernet1/0/1",
        )
        self.conn.set(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec",
            "FC",
        )
        self.conn.apply()

        server = InterfaceServer(self.conn)
        xpath = "/openconfig-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec-mode"
        change = Change(sysrepo.ChangeDeleted(xpath))
        user = {
            "change": [change],
            "sess": self.sess,
        }
        handler = FECModeHandler(server, change)

        handler.validate(user)
        self.assertEqual(handler.original_value, "FC")
        self.assertFalse(handler.if_created)

        handler.apply(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, None)

        handler.revert(user)
        self.sess["running"].apply()
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/ethernet/config/fec"
        data = self.conn.get(xpath)
        self.assertEqual(data, "FC")
        xpath = "/goldstone-interfaces:interfaces/interface[name='Ethernet1/0/1']/name"
        self.conn.get(xpath)


class TestInterfaceServer(XlateTestCase):
    """Tests for InterfaceServer."""

    XLATE_SERVER = InterfaceServer
    XLATE_SERVER_OPT = []
    XLATE_MODULES = ["openconfig-interfaces"]
    MOCK_MODULES = ["goldstone-interfaces", "goldstone-platform"]

    async def test_get_interfaces(self):
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

        def test():
            data = self.conn.get_operational(
                "/openconfig-interfaces:interfaces", strip=False
            )
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
                                    "fec-mode": "openconfig-if-ethernet:FEC_RS528",
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
                                    "fec-mode": "openconfig-if-ethernet:FEC_DISABLED",
                                },
                            },
                        },
                    ]
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)

    async def test_set_enabled(self):
        mock_data_interfaces = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {"admin-status": "UP", "oper-status": "UP"},
                        "component-connection": {"platform": {"component": "port1"}},
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
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            # Set true.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                "iana-if-type:ethernetCsmacd",
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "true",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "UP")

            # Set false.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "false",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "DOWN")

            # Delete.
            name = "Ethernet1/0/1"
            self.conn.delete(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "UP")  # the default value of 'enabled' is "true"

        await self.run_xlate_test(test)

    async def test_set_fec_mode(self):
        mock_data_interfaces = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {"admin-status": "UP", "oper-status": "UP"},
                        "component-connection": {"platform": {"component": "port1"}},
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
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            # Set FEC_FC.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                "iana-if-type:ethernetCsmacd",
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_FC",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "FC")

            # Set FEC_RS528.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_RS528",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "RS")

            # Set FEC_DISABLED.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_DISABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "NONE")

            # Set FEC_RS544.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_RS544",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "RS")

            # Set FEC_DISABLED again to change the translated value.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_DISABLED",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "NONE")

            # Set FEC_RS544_2X_INTERLEAVE.
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
                "FEC_RS544_2X_INTERLEAVE",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, "RS")

            # Delete.
            name = "Ethernet1/0/1"
            self.conn.delete(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/openconfig-if-ethernet:ethernet"
                "/config/fec-mode",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/config/fec"
            data = self.conn.get(xpath)
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_reconcile(self):
        mock_data_interfaces = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Ethernet1/0/1",
                        "state": {"admin-status": "UP", "oper-status": "UP"},
                        "component-connection": {"platform": {"component": "port1"}},
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
                ]
            }
        }
        self.set_mock_oper_data("goldstone-platform", mock_data_platform)

        def test():
            name = "Ethernet1/0/1"
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/type",
                "iana-if-type:ethernetCsmacd",
            )
            self.conn.set(
                f"/openconfig-interfaces:interfaces/interface[name='{name}']/config/enabled",
                "true",
            )
            self.conn.apply()

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status"
            data = self.conn.get(xpath)
            self.assertEqual(data, "UP")

            self.conn.set(xpath, "DOWN")  # make the configuration inconsistent
            self.conn.apply()

            time.sleep(2)

            data = self.conn.get(xpath)
            self.assertEqual(
                data, "UP"
            )  # the primitive model configuration must become consistent again

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
