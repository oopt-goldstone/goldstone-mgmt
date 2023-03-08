"""Tests of OpenROADM translator for openroadm-platform."""

import time
import unittest
from multiprocessing import Process, Queue
import os

from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.errors import Error
from goldstone.xlate.openroadm.device import DeviceServer
from tests.lib import load_configuration_file, XlateTestCase


class TestPlatformServer(XlateTestCase):
    """Tests for PlatformServer.

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
    MOCK_MODULES = ["goldstone-platform"]

    async def test_get_mock(self):
        def test():
            [data] = self.conn.get_operational(
                "/goldstone-platform:components/component[name='SYS']/sys/state/onie-info/vendor"
            )
            self.assertEqual(data, "test_vendor")

        await self.run_xlate_test(test)

    async def test_get_info_vendor(self):
        def test():
            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/vendor"
            )
            self.assertEqual(data, "test_vendor")

        await self.run_xlate_test(test)

    async def test_get_info_model(self):
        def test():
            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/model"
            )
            self.assertEqual(data, "test_part-number")

        await self.run_xlate_test(test)

    async def test_get_info_serial_id(self):
        def test():
            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/serial-id"
            )
            self.assertEqual(data, "test_serial-number")

        await self.run_xlate_test(test)

    async def test_get_info_openroadmversion(self):
        def test():
            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/openroadm-version"
            )
            self.assertEqual(data, "10.0")

        await self.run_xlate_test(test)

    async def test_get_circuit_pack_psu(self):
        def test():
            # Check PSU1 responses
            [data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='PSU1']/model"
            )
            self.assertEqual(data, "PSU1_test_model")
            [data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='PSU1']/serial-id"
            )
            self.assertEqual(data, "PSU1_test_serial")

            # Check PSU2 responses
            [data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='PSU2']/model"
            )
            self.assertEqual(data, "PSU2_test_model")
            [data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='PSU2']/serial-id"
            )
            self.assertEqual(data, "PSU2_test_serial")

            # Check PSU3 responses
            [data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='PSU3']/serial-id"
            )
            self.assertEqual(data, "")

        await self.run_xlate_test(test)

    async def test_get_transceiver(self):
        def test():
            # port1 transceiver (PRESENT)
            [port1_data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']"
            )
            port1_expected = {
                "circuit-pack-name": "port1",
                "vendor": "transceiver_test_vendor_1",
                "model": "transceiver_test_model_1",
                "serial-id": "transceiver_test_serial_1",
                "operational-state": "inService",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(port1_data, port1_expected)

            # port2 transceiver (UNPLUGGED)
            [port2_data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port2']"
            )
            port2_expected = {
                "circuit-pack-name": "port2",
                "vendor": "",
                "model": "",
                "serial-id": "",
                "operational-state": "outOfService",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(port2_data, port2_expected)

            # port16 transceiver (MISSING VENDOR)
            [port16_data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port16']"
            )
            port16_expected = {
                "circuit-pack-name": "port16",
                "vendor": "",
                "model": "transceiver_test_model_16",
                "serial-id": "transceiver_test_serial_16",
                "operational-state": "inService",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(port16_data, port16_expected)

        await self.run_xlate_test(test)

    async def test_get_base_circuit_pack(self):
        def test():
            [base_data] = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='SYS']"
            )
            base_expected = {
                "circuit-pack-name": "SYS",
                "vendor": "test_vendor",
                "model": "test_part-number",
                "serial-id": "test_serial-number",
                "operational-state": "inService",
                "is-pluggable-optics": False,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(base_data, base_expected)

        await self.run_xlate_test(test)

    async def test_set_info(self):
        def test():
            # test node-id success
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/info/node-id", "a123456"
            )
            self.conn.apply()

            data = self.conn.get(
                "/org-openroadm-device:org-openroadm-device/info/node-id"
            )
            self.assertEqual(data, "a123456")

            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/node-id"
            )
            self.assertEqual(data, "a123456")

            # test node-id fail
            self.assertRaises(
                Error,
                self.conn.set,
                "/org-openroadm-device:org-openroadm-device/info/node-id",
                "1",
            )

            # test node-number
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/info/node-number", 1
            )
            self.conn.apply()

            data = self.conn.get(
                "/org-openroadm-device:org-openroadm-device/info/node-number"
            )
            self.assertEqual(data, 1)

            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/node-number"
            )
            self.assertEqual(data, 1)

            # test node-type
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/info/node-type", "xpdr"
            )
            self.conn.apply()

            data = self.conn.get(
                "/org-openroadm-device:org-openroadm-device/info/node-type"
            )
            self.assertEqual(data, "xpdr")

            data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/info/node-type"
            )
            self.assertEqual(data, "xpdr")

        await self.run_xlate_test(test)

    async def test_create_shelf(self):
        def test():
            data = self.conn.get_operational("/goldstone-platform:components/component")
            sys_comp_name = next(
                (
                    comp.get("name")
                    for comp in data
                    if comp.get("state", {}).get("type") == "SYS"
                ),
                None,
            )

            # test provisioning of SYS shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/administrative-state",
                "inService",
            )
            self.conn.apply()

            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']"
            )
            expected = {
                # user provisioned data
                "shelf-name": sys_comp_name,
                "shelf-type": "SYS",
                "administrative-state": "inService",
                "operational-state": "inService",
                # static read only data
                "vendor": "test_vendor",
                "model": "test_part-number",
                "serial-id": "test_serial-number",
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            self.assertDictEqual(data, expected)

            # test failure of arbitrary shelf creation
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/shelves[shelf-name='test_shelf']",
                "test_shelf",
            )
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/shelves[shelf-name='test_shelf']/shelf-type",
                "test_shelf",
            )
            self.conn.set(
                "/org-openroadm-device:org-openroadm-device/shelves[shelf-name='test_shelf']/administrative-state",
                "inService",
            )
            with self.assertRaises(Error):
                self.conn.apply()

        await self.run_xlate_test(test)

    async def test_create_circuit_pack(self):
        def test():
            # find sys component name
            data = self.conn.get_operational("/goldstone-platform:components/component")
            sys_comp_name = next(
                (
                    comp.get("name")
                    for comp in data
                    if comp.get("state", {}).get("type") == "SYS"
                ),
                None,
            )

            # test provisioning of base circuit-pack
            # provisional required SYS shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/administrative-state",
                "inService",
            )
            self.conn.apply()

            # provision base circuit-pack
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/circuit-pack-type",
                "test_type",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/shelf",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/slot",
                "test_slot",
            )
            self.conn.apply()

            data = self.conn.get(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']"
            )
            expected = {
                # user provisioned data
                "circuit-pack-name": sys_comp_name,
                "circuit-pack-type": "test_type",
                "administrative-state": "inService",
                "shelf": sys_comp_name,
                "slot": "test_slot",
            }
            self.assertDictEqual(data, expected)

            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']"
            )
            expected = {
                # user provisioned data
                "circuit-pack-name": sys_comp_name,
                "circuit-pack-type": "test_type",
                "administrative-state": "inService",
                "shelf": sys_comp_name,
                "slot": "test_slot",
                # static read only data
                "operational-state": "inService",
                "vendor": "test_vendor",
                "model": "test_part-number",
                "serial-id": "test_serial-number",
                "is-pluggable-optics": False,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            # data does not have administrative-state, circuit-pack-type, shelf, slot
            self.assertDictEqual(data, expected)

            # test failure of arbitary circuit-pack creation
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='test_pack']",
                "test_pack",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='test_pack']/circuit-pack-type",
                "test_type",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='test_pack']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='test_pack']/shelf",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='test_pack']/slot",
                "test_slot",
            )
            with self.assertRaises(Error):
                self.conn.apply()

        await self.run_xlate_test(test)

    async def test_create_circuit_pack_port(self):
        def test():
            # find sys component name
            data = self.conn.get_operational("/goldstone-platform:components/component")
            sys_comp_name = next(
                (
                    comp.get("name")
                    for comp in data
                    if comp.get("state", {}).get("type") == "SYS"
                ),
                None,
            )

            # test port provisioning
            # provisional required SYS shelf
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/shelf-type",
                "SYS",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/shelves[shelf-name='{sys_comp_name}']/administrative-state",
                "inService",
            )
            self.conn.apply()

            # provision port1 circuit-pack
            # Editing list keys is not supported, edit list instances instead.
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/circuit-pack-type",
                "test_type",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/shelf",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/slot",
                "test_slot",
            )
            self.conn.apply()

            # provision port "1" for port1 circuit-pack
            # Editing list keys is not supported, edit list instances instead.
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/ports[port-name='1']",
                "1",
            )
            self.conn.apply()

            # Got empty data
            [data] = self.conn.get_operational(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/ports[port-name='1']"
            )
            expected = {
                # user provisioned data
                "port-name": "1",
                # static read only data
                "port-direction": "bidirectional",
                "is-physical": True,
                "faceplate-label": "none",
                "operational-state": "inService",
            }
            self.assertDictEqual(data, expected)

            # test failure of arbitary port-name creation
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='port1']/ports[port-name='test_port']",
                "test_port",
            )

            with self.assertRaises(Error):
                self.conn.apply()

            self.conn.discard_changes()

            # test failure of creation of port for non-PIU/TRANSCIEVER circuit-pack
            # provision base circuit-pack
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/circuit-pack-type",
                "test_type",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/administrative-state",
                "inService",
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/shelf",
                sys_comp_name,
            )
            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/slot",
                "test_slot",
            )
            self.conn.apply()
            # test failure of provisioning port for base circuit-pack

            self.conn.set(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{sys_comp_name}']/ports[port-name='1']",
                "1",
            )

            with self.assertRaises(Error):
                self.conn.apply()

            self.conn.discard_changes()

            # Test deletion of circuit-packs
            # Get the list of circuit-pack-name in running datastore
            cp_name_list = self.conn.get(
                "/org-openroadm-device:org-openroadm-device/circuit-packs/circuit-pack-name"
            )

            # delete the circuit-packs in running datastore
            for cp_name in cp_name_list:
                self.conn.delete(
                    f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']"
                )
                self.conn.apply()

            # check running datastore that all circuit-packs are deleted
            data = self.conn.get(
                f"/org-openroadm-device:org-openroadm-device/circuit-packs"
            )
            self.assertEqual(None, data)

        await self.run_xlate_test(test)

    async def test_get_optical_operational_mode_profile(self):
        def test():
            profile_data = self.conn.get_operational(
                "/org-openroadm-device:org-openroadm-device/optical-operational-mode-profile"
            )

            # check Open ROADM profile display with the profile list in JSON file
            for mode in self.server.operational_modes:
                my_profile_name = mode.get("openroadm", {}).get("profile-name")
                if my_profile_name != None:
                    self.assertIn(my_profile_name, profile_data)

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
