"""Tests of OpenROADM translator for goldstone-transponder"""

import time
import unittest
from multiprocessing import Process, Queue
import os

import libyang
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import Error
from goldstone.xlate.openroadm.device import DeviceServer

from .lib import *
from tests.lib import load_configuration_file, XlateTestCase


class TestTransponderServer(XlateTestCase):
    """Tests for TransponderServer.

    Notes:
        - Mock servers take less than a second to complete the preparation. All test methods should wait a second after
          calling set_mock_oper_data() to start test.
        - Some test methods contain several tests instead of one test. It is to reduce the time to test. All test
          methods take over a second for each because of the time to wait mock servers.
    """

    OPERATIONAL_MODES_PATH = os.path.dirname(__file__) + "/operational-modes.json"
    PLATFORM_INFO_PATH = os.path.dirname(__file__) + "/platform.json"
    operational_modes = load_configuration_file(OPERATIONAL_MODES_PATH)
    platform_info = load_configuration_file(PLATFORM_INFO_PATH)
    XLATE_SERVER = DeviceServer
    XLATE_SERVER_OPT = [operational_modes, platform_info]
    XLATE_MODULES = ["org-openroadm-device"]
    MOCK_MODULES = [
        "goldstone-interfaces",
        "goldstone-platform",
        "goldstone-transponder",
    ]

    async def test_get_mock(self):
        def test():
            # ensure goldstone-transponder is mocked by MockGSTransponderServer
            [data] = self.conn.get_operational(
                "/goldstone-transponder:modules/module[name='piu1']/name"
            )
            self.assertEqual(data, "piu1")

        await self.run_xlate_test(test)

    async def test_get_otsi_entries(self):
        def test():
            # Setup basic shelf info to start with

            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "myshelftype",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )
            self.conn.apply()

            piu_val = "piu1"
            or_val = "Interface1/1/1"
            slot_val = 0
            setup_otsi_connections(self.conn, piu_val, or_val, slot_val)

            # While we are here on the first (piu1) connection, verify that manual
            # transmit power connections can be set and read back
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/type",
                "org-openroadm-interfaces:otsi",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/org-openroadm-optical-tributary-signal-interfaces:otsi/transmit-power",
                "-123.46",
            )
            self.conn.apply()
            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu1']"
            )

            # With the sets above, we will not see the values from the
            # operational data (these will be present on real hardware).
            # Instead we verify from the goldstone running datastore to
            # confirm correct handler functionality
            data = self.conn.get(
                f"/goldstone-transponder:modules/module[name='{piu_val}']/network-interface[name='0']/config/output-power"
            )
            self.assertEqual(data, -123.46)

            # Also test that a subsequent modify is handled
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/org-openroadm-optical-tributary-signal-interfaces:otsi/transmit-power",
                "5.43",
            )
            self.conn.apply()

            data = self.conn.get(
                f"/goldstone-transponder:modules/module[name='{piu_val}']/network-interface[name='{0}']/config/output-power"
            )
            self.assertEqual(data, 5.43)

            # and test that deletes are also handled
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/org-openroadm-optical-tributary-signal-interfaces:otsi/transmit-power"
            )
            self.conn.apply()

            data = self.conn.get(
                f"/goldstone-transponder:modules/module[name='{piu_val}']/network-interface[name='0']/config/output-power"
            )
            self.assertEqual(data, None)

            # Now move to just testing the oper values.
            # Since this is strictly a testing environment, the values reflect the hard coded mock data values
            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/name"
            )
            self.assertEqual(data, or_val)

            # Now move on to the next piu.  Sets are done from running mode
            piu_val = "piu2"
            or_val = "or_val2"
            slot_val = 0
            setup_otsi_connections(self.conn, piu_val, or_val, slot_val)

            # Queries are done from operational mode
            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/name"
            )
            self.assertEqual(data, or_val)

            # Now move on to the next piu.  Sets are done from running mode
            piu_val = "piu3"
            or_val = "or_val3"
            slot_val = 0
            setup_otsi_connections(self.conn, piu_val, or_val, slot_val)

            # Queries are done from operational mode
            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/name"
            )
            self.assertEqual(data, or_val)

            # Now move on to the next piu.  Sets are done from running mode
            piu_val = "piu4"
            or_val = "or_val4"
            slot_val = 0
            setup_otsi_connections(self.conn, piu_val, or_val, slot_val)

            # Queries are done from operational mode
            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{or_val}']/name"
            )
            self.assertEqual(data, or_val)

            # With the PIUs configured as above, go ahead and check the PIU responses
            piu1_data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu1']"
            )

            piu1_expected = {
                "circuit-pack-name": "piu1",
                "vendor": "piu1_vendor_name",
                "model": "piu1_vendor_pn",
                "serial-id": "piu1_vendor_sn",
                "operational-state": "inService",
                "slot": "0",
                "subSlot": "piu1",
                "ports": [
                    {
                        "port-name": "1",
                        "operational-state": "inService",
                        "port-direction": "bidirectional",
                        "faceplate-label": "none",
                        "is-physical": True,
                    }
                ],
                "shelf": "SYS",
                "administrative-state": "inService",
                "circuit-pack-type": "cpType",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(piu1_data[0], piu1_expected)

            piu2_data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu2']"
            )
            piu2_expected = {
                "circuit-pack-name": "piu2",
                "vendor": "piu2_vendor_name",
                "model": "",
                "serial-id": "",
                "operational-state": "degraded",
                "slot": "0",
                "subSlot": "piu2",
                "ports": [
                    {
                        "port-name": "1",
                        "operational-state": "inService",
                        "port-direction": "bidirectional",
                        "faceplate-label": "none",
                        "is-physical": True,
                    }
                ],
                "shelf": "SYS",
                "administrative-state": "inService",
                "circuit-pack-type": "cpType",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(piu2_data[0], piu2_expected)

            piu3_data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu3']"
            )
            piu3_expected = {
                "circuit-pack-name": "piu3",
                "vendor": "piu3_vendor_name",
                "model": "",
                "serial-id": "piu3_vendor_sn",
                "operational-state": "outOfService",
                "slot": "0",
                "subSlot": "piu3",
                "ports": [
                    {
                        "port-name": "1",
                        "operational-state": "inService",
                        "port-direction": "bidirectional",
                        "faceplate-label": "none",
                        "is-physical": True,
                    }
                ],
                "shelf": "SYS",
                "administrative-state": "inService",
                "circuit-pack-type": "cpType",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(piu3_data[0], piu3_expected)

            piu4_data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu4']"
            )
            piu4_expected = {
                "circuit-pack-name": "piu4",
                "vendor": "",
                "model": "piu4_vendor_pn",
                "serial-id": "",
                "operational-state": "degraded",
                "slot": "0",
                "subSlot": "piu4",
                "ports": [
                    {
                        "port-name": "1",
                        "operational-state": "inService",
                        "port-direction": "bidirectional",
                        "faceplate-label": "none",
                        "is-physical": True,
                    }
                ],
                "shelf": "SYS",
                "administrative-state": "inService",
                "circuit-pack-type": "cpType",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(piu4_data[0], piu4_expected)

        await self.run_xlate_test(test)

    async def test_otsi_explicit_provision(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and interface
            interface_name = "otsi_new"
            setup_otsi_connections(self.conn, "piu1", interface_name, 1)

            # test explicit provisioning of otsi-rate, modulation-format, and fec
            piu_xpath = f"/org-openroadm-device:org-openroadm-device/interface[name='{interface_name}']"
            self.conn.set(piu_xpath + "/type", "org-openroadm-interfaces:otsi")
            self.conn.set(piu_xpath + "/administrative-state", "inService")
            self.conn.set(
                piu_xpath
                + "/org-openroadm-optical-tributary-signal-interfaces:otsi/provision-mode",
                "explicit",
            )
            self.conn.set(
                piu_xpath
                + "/org-openroadm-optical-tributary-signal-interfaces:otsi/otsi-rate",
                "org-openroadm-common-optical-channel-types:R100G-otsi",
            )
            self.conn.set(
                piu_xpath
                + "/org-openroadm-optical-tributary-signal-interfaces:otsi/modulation-format",
                "dp-qam16",
            )
            self.conn.set(
                piu_xpath
                + "/org-openroadm-optical-tributary-signal-interfaces:otsi/fec",
                "org-openroadm-common-types:ofec",
            )

            self.conn.apply()

            data = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            [data] = data
            expected = {
                "name": "0",
                "line-rate": "100g",
                "modulation-format": "dp-16-qam",
                "fec-type": "ofec",
                "output-power": -123.456789,
            }
            self.assertDictEqual(expected, data)

            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{interface_name}']/org-openroadm-optical-tributary-signal-interfaces:otsi"
            )
            [data] = data
            expected = {
                "provision-mode": "explicit",
                "otsi-rate": "org-openroadm-common-optical-channel-types:R100G-otsi",
                "fec": "org-openroadm-common-types:ofec",
                "modulation-format": "dp-qam16",
            }
            self.assertDictEqual(expected, data)

            # test deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{interface_name}']"
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{interface_name}']",
                default=None,
            )
            self.assertEqual(None, data)

        await self.run_xlate_test(test)

    async def test_set_opt_oper_mode(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and interface
            setup_otsi_connections(self.conn, "piu1", "piu1", 1)

            # test non-existent profile
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/type",
                "org-openroadm-interfaces:otsi",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/provision-mode",
                "profile",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/optical-operational-mode",
                "foo",
            )
            with self.assertRaises(Error):
                self.conn.apply()

            self.conn.discard_changes()

            # # test ORBKD-W-400G-1000X profile
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/type",
                "org-openroadm-interfaces:otsi",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/provision-mode",
                "profile",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/optical-operational-mode",
                "ORBKD-W-400G-1000X",
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            [data] = data
            expected = {
                "name": "0",
                "line-rate": "400g",
                "modulation-format": "dp-16-qam-ps",
                "fec-type": "ofec",
                "output-power": -123.456789,
            }
            self.assertDictEqual(expected, data)

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi"
            )
            [data] = data
            expected = {
                "provision-mode": "profile",
                "optical-operational-mode": "ORBKD-W-400G-1000X",
            }
            self.assertDictEqual(expected, data)

            # test deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/optical-operational-mode"
            )
            self.conn.apply()

            [data] = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            expected = {"name": "0", "output-power": -123.456789}
            self.assertDictEqual(expected, data)

            [data] = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi"
            )
            expected = {"provision-mode": "profile"}
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_set_frequency(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and interface
            setup_otsi_connections(self.conn, "piu1", "piu1", 1)

            # test set frequency
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/frequency",
                123.456,
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            [data] = data
            expected = {
                "name": "0",
                "tx-laser-freq": 123456000000000,
                "output-power": -123.456789,
            }
            self.assertDictEqual(expected, data)

            # test deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='piu1']/org-openroadm-optical-tributary-signal-interfaces:otsi/frequency"
            )
            self.conn.apply()

            [data] = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            expected = {"name": "0", "output-power": -123.456789}
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_get_client_eth_speed(self):
        def setup_eth_speed(self, conn, slot, piu, if_name, or_port, or_speed):
            setup_eth_port_config(conn, slot, piu, if_name, or_port)
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/org-openroadm-ethernet-interfaces:ethernet/speed",
                f"{or_speed}",
            )
            self.conn.apply()

        def test():
            setup_shelf_and_sys(self.conn)

            # These names are from the Openroadm side
            slot = 0
            piu = "piu1"
            ifname = "Interface1/1/1"
            port = "port1"
            speed = 100000
            setup_eth_speed(self, self.conn, slot, piu, ifname, port, speed)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/signal-rate"
            )
            self.assertEqual(data, "100-gbe")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.assertEqual(data[0], 100000)

            slot = 0
            piu = "piu2"
            ifname = "Interface1/1/2"
            port = "port5"
            speed = 200000
            setup_eth_speed(self, self.conn, slot, piu, ifname, port, speed)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/signal-rate"
            )
            self.assertEqual(data, "200-gbe")

            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.assertEqual(data[0], 200000)

            slot = 0
            piu = "piu3"
            ifname = "Interface2/1/1"
            port = "port9"
            speed = 400000
            setup_eth_speed(self, self.conn, slot, piu, ifname, port, speed)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/signal-rate"
            )
            self.assertEqual(data, "400-gbe")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.assertEqual(data[0], 400000)

            slot = 0
            piu = "piu1"
            ifname = "Interface1/1/1"
            port = "port1"
            speed = 0
            setup_eth_speed(self, self.conn, slot, piu, ifname, port, speed)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/signal-rate"
            )
            self.assertEqual(data, "unknown")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet"
            )
            # zero speed entries need extra help
            self.assertEqual(data[0].get("speed"), 0)

            slot = 0
            piu = "piu4"
            ifname = "Interface2/1/5"
            port = "port13"
            speed = 100000
            setup_eth_speed(self, self.conn, slot, piu, ifname, port, speed)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/signal-rate"
            )
            self.assertEqual(data, "100-gbe")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.assertEqual(data[0], 100000)

            # and test that deletes are also handled
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.conn.apply()
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/speed"
            )
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_get_client_eth_fec(self):
        def setup_eth_fec(self, conn, slot, piu, if_name, or_port, or_fec):
            setup_eth_port_config(conn, slot, piu, if_name, or_port)
            conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{if_name}']/org-openroadm-ethernet-interfaces:ethernet/fec",
                f"{or_fec}",
            )
            conn.apply()

        def test():
            setup_shelf_and_sys(self.conn)

            # These names are from the Openroadm side
            slot = 0
            piu = "piu1"
            ifname = "Interface1/1/1"
            port = "port1"
            fec = "org-openroadm-common-types:off"
            setup_eth_fec(self, self.conn, slot, piu, ifname, port, fec)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/fec-type"
            )
            self.assertEqual(data, "none")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/fec"
            )
            self.assertEqual(data[0], "org-openroadm-common-types:off")

            slot = 0
            piu = "piu3"
            ifname = "Interface2/1/1"
            port = "port1"
            fec = "org-openroadm-common-types:rsfec"
            setup_eth_fec(self, self.conn, slot, piu, ifname, port, fec)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/fec-type"
            )
            self.assertEqual(data, "rs")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/fec"
            )
            self.assertEqual(data[0], "org-openroadm-common-types:rsfec")

            slot = 0
            piu = "piu4"
            ifname = "Interface2/1/5"
            port = "port1"
            fec = "org-openroadm-common-types:baser"
            setup_eth_fec(self, self.conn, slot, piu, ifname, port, fec)

            # Verify that the goldstone running and openroadm operational
            # data stores have the info
            gs_piu, gs_port = self.server._translate_circuit_pack_name(
                self.server.or_port_map, port
            )
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/fec-type"
            )
            self.assertEqual(data, "fc")
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/fec"
            )
            self.assertEqual(data[0], "org-openroadm-common-types:baser")

            # and test that deletes are also handled
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/fec"
            )
            self.conn.apply()
            data = self.server.get_running_data(
                f"/goldstone-transponder:modules/module[name='{gs_piu}']/host-interface[name='{gs_port}']/config/fec-type"
            )
            self.assertEqual(data, None)
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/fec"
            )
            self.assertEqual(data, None)

        await self.run_xlate_test(test)

    async def test_get_client_eth_cur_speed(self):
        def test():
            setup_shelf_and_sys(self.conn)

            slot = 0
            piu = "piu1"
            ifname = "Interface1/1/1"
            port = "port1"
            setup_eth_port_config(self.conn, slot, piu, ifname, port)
            # Since we are just checking RO oper data, no 'set' is required
            # values come from the mock goldstone-transponder data
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/curr-speed"
            )
            self.assertEqual(data[0], "100000")

            slot = 0
            piu = "piu2"
            ifname = "Interface1/1/5"
            port = "port5"
            setup_eth_port_config(self.conn, slot, piu, ifname, port)
            # Since we are just checking RO oper data, no 'set' is required
            # values come from the mock goldstone-transponder data
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/curr-speed"
            )
            self.assertEqual(data[0], "200000")

            slot = 0
            piu = "piu3"
            ifname = "Interface2/1/1"
            port = "port9"
            setup_eth_port_config(self.conn, slot, piu, ifname, port)
            # Since we are just checking RO oper data, no 'set' is required
            # values come from the mock goldstone-transponder data
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/curr-speed"
            )
            self.assertEqual(data[0], "400000")

            slot = 0
            piu = "piu4"
            ifname = "Interface2/1/8"
            port = "port16"
            setup_eth_port_config(self.conn, slot, piu, ifname, port)
            # Since we are just checking RO oper data, no 'set' is required
            # values come from the mock goldstone-transponder data
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='{ifname}']/org-openroadm-ethernet-interfaces:ethernet/curr-speed"
            )
            self.assertEqual(data[0], "100000")

            # Bad lookups are handled ok
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device/interface[name='foofoo']/org-openroadm-ethernet-interfaces:ethernet/curr-speed"
            )
            self.assertEqual(data, None)

            # And verify that top level get works as well
            data = self.server.get_operational_data(
                f"/org-openroadm-device:org-openroadm-device"
            )
            p1 = libyang.xpath_get(
                data, "interface[name='Interface1/1/1']/ethernet/curr-speed"
            )
            self.assertEqual(int(p1), 100000)
            p2 = libyang.xpath_get(
                data, "interface[name='Interface1/1/5']/ethernet/curr-speed"
            )
            self.assertEqual(int(p2), 200000)
            p3 = libyang.xpath_get(
                data, "interface[name='Interface2/1/1']/ethernet/curr-speed"
            )
            self.assertEqual(int(p3), 400000)
            p4 = libyang.xpath_get(
                data, "interface[name='Interface2/1/8']/ethernet/curr-speed"
            )
            self.assertEqual(int(p4), 100000)

        await self.run_xlate_test(test)

    async def test_otsig_write(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and otsi interface
            setup_otsi_connections(self.conn, "piu1", "otsi-piu1", 1)

            # setup circuit-pack and otsi-g interface
            # supporting-circuit-pack-name will be derived from supporting-interface-list for high-level-interfaces in Phase 2
            setup_interface(self.conn, "otsig-piu1", "piu1")

            # setup supporting interface
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/supporting-interface-list",
                "otsi-piu1",
            )

            # test provision otsig interface
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/type",
                "org-openroadm-interfaces:otsi-group",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/org-openroadm-otsi-group-interfaces:otsi-group/group-rate",
                "org-openroadm-common-optical-channel-types:R400G-otsi",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/org-openroadm-otsi-group-interfaces:otsi-group/group-id",
                1,
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/org-openroadm-otsi-group-interfaces:otsi-group"
            )
            [data] = data
            expected = {
                "group-rate": "org-openroadm-common-optical-channel-types:R400G-otsi",
                "group-id": 1,
            }
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_set_otuc_loopback(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and otsi interface
            setup_otsi_connections(self.conn, "piu1", "otsi-piu1", 1)

            # setup circuit-pack and otsi-g interface
            # supporting-circuit-pack-name will be derived from supporting-interface-list for high-level-interfaces
            setup_interface(self.conn, "otsig-piu1", "piu1")

            # setup supporting interface connection
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/supporting-interface-list",
                "otsi-piu1",
            )

            # setup otuc interface
            setup_interface(self.conn, "otuc-piu1", "piu1")

            # setup supporting interface connection
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/supporting-interface-list",
                "otsig-piu1",
            )

            # test provision otuc loopback
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/type",
                "org-openroadm-interfaces:otnOtu",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/rate",
                "org-openroadm-otn-common-types:OTUCn",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/otucn-n-rate",
                4,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/maint-loopback/enabled",
                True,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/maint-loopback/type",
                "fac",
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            [data] = data
            expected = {
                "name": "0",
                "output-power": -123.456789,
                "loopback-type": "shallow",
            }
            self.assertDictEqual(expected, data)

            # test enabled = false mapping
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/org-openroadm-otn-otu-interfaces:otu/maint-loopback/enabled",
                False,
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/goldstone-transponder:modules/module[name='piu1']/network-interface[name='0']/config"
            )
            [data] = data
            expected = {
                "name": "0",
                "output-power": -123.456789,
                "loopback-type": "none",
            }
            self.assertDictEqual(expected, data)

            # test otucn interface deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']"
            )
            self.conn.apply()

            data = self.server.get_running_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']"
            )
            self.assertEqual(None, data)

        await self.run_xlate_test(test)

    async def test_set_oducn(self):
        def test():
            # setup 'SYS' shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='SYS']/administrative-state",
                "inService",
            )

            # setup circuit-pack and otsi interface
            setup_otsi_connections(self.conn, "piu1", "otsi-piu1", 1)

            # setup circuit-pack and otsi-g interface
            # supporting-circuit-pack-name will be derived from supporting-interface-list for high-level-interfaces
            setup_interface(self.conn, "otsig-piu1", "piu1")

            # setup supporting interface connection (otsig -> otsi)
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otsig-piu1']/supporting-interface-list",
                "otsi-piu1",
            )

            # setup otuc interface
            setup_interface(self.conn, "otuc-piu1", "piu1")

            # setup supporting interface connection (otuc -> otsig)
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='otuc-piu1']/supporting-interface-list",
                "otsig-piu1",
            )

            # setup oduc interface
            setup_interface(self.conn, "oduc-piu1", "piu1")

            # setup supporting interface connection (oduc -> otuc)
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/supporting-interface-list",
                "otuc-piu1",
            )

            # test provision of odu
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/type",
                "org-openroadm-interfaces:otnOdu",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/rate",
                "org-openroadm-otn-common-types:ODUCn",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/oducn-n-rate",
                4,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/odu-function",
                "org-openroadm-otn-common-types:ODU-TTP",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu/monitoring-mode",
                "terminated",
            )

            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']/org-openroadm-otn-odu-interfaces:odu"
            )
            [data] = data
            expected = {
                "rate": "org-openroadm-otn-common-types:ODUCn",
                "oducn-n-rate": 4,
                "odu-function": "org-openroadm-otn-common-types:ODU-TTP",
                "monitoring-mode": "terminated",
            }
            self.assertDictEqual(expected, data)

            # test deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']"
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='oduc-piu1']"
            )
            self.assertEqual(None, data)

        await self.run_xlate_test(test)

    async def test_set_odu_connection(self):
        def test():
            setup_interface_hierarchy(self.conn)
            setup_shelf_and_sys(self.conn)
            setup_eth_port_config(self.conn, 0, "piu1", "eth-1", "port1")

            # nw-odu (1 of 4 in 400G operation)
            setup_interface(
                self.conn,
                "odu-1.1",
                "piu1",
                type="org-openroadm-interfaces:otnOdu",
                sup_intf="oduc-piu1",
            )
            # client-odu
            setup_interface(
                self.conn,
                "odu-client-port1",
                "piu1",
                type="org-openroadm-interfaces:otnOdu",
                sup_intf="eth-1",
            )

            # required for odu-connection
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/info/node-type", "xpdr"
            )
            self.conn.apply()

            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection']/direction",
                "unidirectional",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection']/source/src-if",
                "odu-1.1",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection']/destination/dst-if",
                "odu-client-port1",
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection']"
            )
            [data] = data
            expected = {
                "connection-name": "test_connection",
                "direction": "unidirectional",
                "source": {"src-if": "odu-1.1"},
                "destination": {"dst-if": "odu-client-port1"},
            }
            self.assertDictEqual(expected, data)

            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']/direction",
                "unidirectional",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']/source/src-if",
                "odu-client-port1",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']/destination/dst-if",
                "odu-1.1",
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']"
            )
            [data] = data
            expected = {
                "connection-name": "test_connection_2",
                "direction": "unidirectional",
                "source": {"src-if": "odu-client-port1"},
                "destination": {"dst-if": "odu-1.1"},
            }
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_odu_static_mappings(self):
        def test():
            setup_interface_hierarchy(self.conn)
            setup_shelf_and_sys(self.conn)
            setup_eth_port_config(self.conn, 0, "piu1", "eth-1", "port1")

            # nw-odu
            setup_interface(
                self.conn,
                "odu-1.1",
                "piu1",
                type="org-openroadm-interfaces:otnOdu",
                sup_intf="oduc-piu1",
            )

            [data] = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='odu-1.1']/org-openroadm-otn-odu-interfaces:odu"
            )
            expected = {"no-oam-function": None, "no-maint-testsignal-function": None}
            self.assertDictEqual(expected, data)

            # client-odu
            setup_interface(
                self.conn,
                "odu-client-port1",
                "piu1",
                type="org-openroadm-interfaces:otnOdu",
                sup_intf="eth-1",
            )

            [data] = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='odu-client-port1']/org-openroadm-otn-odu-interfaces:odu"
            )
            expected = {"no-oam-function": None, "no-maint-testsignal-function": None}
            self.assertDictEqual(expected, data)

            # test deletion
            self.conn.delete(
                f"/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']"
            )
            self.conn.apply()

            data = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/odu-connection[connection-name='test_connection_2']"
            )
            self.assertEqual(None, data)

        await self.run_xlate_test(test)

    async def test_set_parent_odu_alloc(self):
        def test():
            setup_interface_hierarchy(self.conn)
            setup_shelf_and_sys(self.conn)
            setup_eth_port_config(self.conn, 0, "piu1", "eth-1", "port1")

            # nw-odu
            setup_interface(
                self.conn,
                "odu-1.1",
                "piu1",
                type="org-openroadm-interfaces:otnOdu",
                sup_intf="oduc-piu1",
            )

            # set parent odu allocation
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/interface[name='odu-1.1']/org-openroadm-otn-odu-interfaces:odu/parent-odu-allocation/trib-port-number",
                1,
            )
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/interface[name='odu-1.1']/org-openroadm-otn-odu-interfaces:odu/parent-odu-allocation/opucn-trib-slots",
                ["1.1", "1.2"],
            )
            self.conn.apply()

            [data] = self.server.get_operational_data(
                "/org-openroadm-device:org-openroadm-device/interface[name='odu-1.1']/org-openroadm-otn-odu-interfaces:odu/parent-odu-allocation"
            )
            expected = {"trib-port-number": 1, "opucn-trib-slots": ["1.1", "1.2"]}
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
