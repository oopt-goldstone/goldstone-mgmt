import asyncio
import logging
import unittest
from multiprocessing import Process, Queue
import os

import libyang
from goldstone.xlate.openroadm.main import load_configuration_file
from goldstone.xlate.openroadm.pm import PMServer
from goldstone.xlate.openroadm.device import DeviceServer

from .lib import *


class TestPMServer(XlateTestCase):
    async def asyncSetUp(self):
        OPERATIONAL_MODES_PATH = os.path.dirname(__file__) + "/operational-modes.json"
        PLATFORM_INFO_PATH = os.path.dirname(__file__) + "/platform.json"
        operational_modes = load_configuration_file(OPERATIONAL_MODES_PATH)
        platform_info = load_configuration_file(PLATFORM_INFO_PATH)
        XLATE_SERVER_OPT = [operational_modes, platform_info]
        XLATE_MODULES = ["org-openroadm-device", "org-openroadm-pm"]
        MOCK_MODULES = ["goldstone-platform", "goldstone-transponder"]

        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        for module in MOCK_MODULES:
            self.conn.delete_all(module)
        for module in XLATE_MODULES:
            self.conn.delete_all(module)
        self.conn.apply()

        self.q = Queue()
        self.process = Process(target=run_mock_server, args=(self.q, MOCK_MODULES))
        self.process.start()
        time.sleep(5)  # wait for setting up mock server

        self.server = PMServer(self.conn, reconciliation_interval=1)
        device_server = DeviceServer(
            self.conn, operational_modes, platform_info, reconciliation_interval=1
        )
        servers = [self.server, device_server]

        self.tasks = [
            asyncio.create_task(c) for server in servers for c in await server.start()
        ]

    async def test_get_optical_power_input(self):
        def test():
            setup_interface_hierarchy(self.conn)

            data = self.conn.get_operational(
                "/org-openroadm-pm:current-pm-list/current-pm-entry/current-pm[type='opticalPowerInput']",
                strip=False,
            )
            expected = {
                "current-pm-list": {
                    "current-pm-entry": [
                        {
                            "pm-resource-type": "port",
                            "pm-resource-type-extension": "",
                            "pm-resource-instance": "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu1']/ports[port-name='1']",
                            "current-pm": [
                                {
                                    "type": "opticalPowerInput",
                                    "extension": "",
                                    "location": "nearEnd",
                                    "direction": "rx",
                                    "measurement": [
                                        {
                                            "granularity": "notApplicable",
                                            "pmParameterValue": 70.0,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_get_optical_power_output(self):
        def test():
            setup_interface_hierarchy(self.conn)

            data = self.conn.get_operational(
                "/org-openroadm-pm:current-pm-list/current-pm-entry/current-pm[type='opticalPowerOutput']",
                strip=False,
            )
            expected = {
                "current-pm-list": {
                    "current-pm-entry": [
                        {
                            "pm-resource-type": "port",
                            "pm-resource-type-extension": "",
                            "pm-resource-instance": "/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='piu1']/ports[port-name='1']",
                            "current-pm": [
                                {
                                    "type": "opticalPowerOutput",
                                    "extension": "",
                                    "location": "nearEnd",
                                    "direction": "tx",
                                    "measurement": [
                                        {
                                            "granularity": "notApplicable",
                                            "pmParameterValue": -20.1,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def test_get_prefec_ber(self):
        def test():
            setup_interface_hierarchy(self.conn)

            data = self.conn.get_operational(
                "/org-openroadm-pm:current-pm-list/current-pm-entry/current-pm[type='preFECbitErrorRate']",
                strip=False,
            )
            expected = {
                "current-pm-list": {
                    "current-pm-entry": [
                        {
                            "pm-resource-type": "interface",
                            "pm-resource-type-extension": "",
                            "pm-resource-instance": "/org-openroadm-device:org-openroadm-device/interface[name='otsi-piu1']",
                            "current-pm": [
                                {
                                    "type": "preFECbitErrorRate",
                                    "extension": "",
                                    "location": "nearEnd",
                                    "direction": "rx",
                                    "measurement": [
                                        {
                                            "granularity": "notApplicable",
                                            "pmParameterValue": 0.00061805872246623,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
            self.assertDictEqual(expected, data)

        await self.run_xlate_test(test)

    async def asyncTearDown(self):
        await call(self.server.stop)
        self.tasks = [t.cancel() for t in self.tasks]
        self.conn.stop()
        self.q.put({"type": "stop"})
        self.process.join()
