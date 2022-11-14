"""Tests of OpenConfig translater for openconfig-telemetry."""

import unittest
from libyang.keyed_list import KeyedList
from goldstone.xlate.openconfig.telemetry import (
    DynamicSubscriptionFactory,
    TelemetryServer,
)
from tests.lib import XlateTestCase


class TestDynamicSubscriptionFactory(unittest.TestCase):
    """Tests for DynamicSubscriptionFactory."""

    def test_empty_subscriptions(self):
        gs_subscribe_requests = KeyedList(
            [
                {
                    "id": 1,
                    "state": {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                    },
                    "subscriptions": {
                        "subscription": KeyedList([], "id"),
                    },
                },
            ],
            "id",
        )
        gs = {"subscribe-requests": gs_subscribe_requests}
        dsf = DynamicSubscriptionFactory()
        data = dsf.create(gs)
        expected = []
        self.assertEqual(data, expected)

    def test_one_subscription(self):
        gs_subscribe_requests = KeyedList(
            [
                {
                    "id": 1,
                    "state": {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                    },
                    "subscriptions": {
                        "subscription": KeyedList(
                            [
                                {
                                    "id": 1,
                                    "state": {
                                        "id": 1,
                                        "path": "/test/path",
                                    },
                                },
                            ],
                            "id",
                        ),
                    },
                },
            ],
            "id",
        )
        gs = {"subscribe-requests": gs_subscribe_requests}
        dsf = DynamicSubscriptionFactory()
        data = dsf.create(gs)
        expected = [
            {
                "id": 4294967297,
                "state": {
                    "id": 4294967297,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path",
                            "state": {
                                "path": "/test/path",
                            },
                        },
                    ],
                },
            },
        ]
        self.assertEqual(data, expected)

    def test_multiple_subscriptions(self):
        gs_subscribe_requests = KeyedList(
            [
                {
                    "id": 1,
                    "state": {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                    },
                    "subscriptions": {
                        "subscription": KeyedList(
                            [
                                {
                                    "id": 1,
                                    "state": {
                                        "id": 1,
                                        "path": "/test/path",
                                    },
                                },
                            ],
                            "id",
                        ),
                    },
                },
                {
                    "id": 2,
                    "state": {
                        "id": 2,
                        "mode": "STREAM",
                        "updates-only": False,
                    },
                    "subscriptions": {
                        "subscription": KeyedList(
                            [
                                {
                                    "id": 1,
                                    "state": {
                                        "id": 1,
                                        "path": "/test/path/one",
                                        "mode": "SAMPLE",
                                    },
                                },
                                {
                                    "id": 2,
                                    "state": {
                                        "id": 2,
                                        "path": "/test/path/two",
                                        "mode": "SAMPLE",
                                        "sample-interval": 5 * 1000 * 1000 * 1000,
                                    },
                                },
                                {
                                    "id": 3,
                                    "state": {
                                        "id": 3,
                                        "path": "/test/path/three",
                                        "mode": "SAMPLE",
                                        "sample-interval": 5 * 1000 * 1000 * 1000,
                                        "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                                    },
                                },
                                {
                                    "id": 4,
                                    "state": {
                                        "id": 4,
                                        "path": "/test/path/four",
                                        "mode": "SAMPLE",
                                        "sample-interval": 5 * 1000 * 1000 * 1000,
                                        "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                                        "suppress-redundant": True,
                                    },
                                },
                            ],
                            "id",
                        ),
                    },
                },
            ],
            "id",
        )
        gs = {"subscribe-requests": gs_subscribe_requests}
        dsf = DynamicSubscriptionFactory()
        data = dsf.create(gs)
        expected = [
            {
                "id": 4294967296 + 1,
                "state": {
                    "id": 4294967296 + 1,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path",
                            "state": {
                                "path": "/test/path",
                            },
                        },
                    ],
                },
            },
            {
                "id": 8589934592 + 1,
                "state": {
                    "id": 8589934592 + 1,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path/one",
                            "state": {
                                "path": "/test/path/one",
                            },
                        },
                    ],
                },
            },
            {
                "id": 8589934592 + 2,
                "state": {
                    "id": 8589934592 + 2,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                    "sample-interval": 5 * 1000 * 1000 * 1000,
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path/two",
                            "state": {
                                "path": "/test/path/two",
                            },
                        },
                    ],
                },
            },
            {
                "id": 8589934592 + 3,
                "state": {
                    "id": 8589934592 + 3,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                    "sample-interval": 5 * 1000 * 1000 * 1000,
                    "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path/three",
                            "state": {
                                "path": "/test/path/three",
                            },
                        },
                    ],
                },
            },
            {
                "id": 8589934592 + 4,
                "state": {
                    "id": 8589934592 + 4,
                    "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                    "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                    "sample-interval": 5 * 1000 * 1000 * 1000,
                    "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                    "suppress-redundant": True,
                },
                "sensor-paths": {
                    "sensor-path": [
                        {
                            "path": "/test/path/four",
                            "state": {
                                "path": "/test/path/four",
                            },
                        },
                    ],
                },
            },
        ]
        self.assertEqual(data, expected)


class TestTelemetryServer(XlateTestCase):
    """Tests for TelemetryServer.

    Notes:
        - Mock servers take less than a second to complete the preparation. All test methods should wait a second after
          calling set_mock_oper_data() to start test.
    """

    XLATE_SERVER = TelemetryServer
    XLATE_SERVER_OPT = []
    XLATE_MODULES = ["openconfig-telemetry"]
    MOCK_MODULES = ["goldstone-telemetry"]

    async def test_get(self):
        mock_data_telemetry = {
            "subscribe-requests": {
                "subscribe-request": [
                    {
                        "id": 1,
                        "state": {
                            "id": 1,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 1,
                                    "state": {
                                        "id": 1,
                                        "path": "/test/path/one",
                                        "mode": "SAMPLE",
                                    },
                                },
                                {
                                    "id": 2,
                                    "state": {
                                        "id": 2,
                                        "path": "/test/path/two",
                                        "mode": "SAMPLE",
                                        "sample-interval": 5 * 1000 * 1000 * 1000,
                                        "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                                        "suppress-redundant": True,
                                    },
                                },
                            ],
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("goldstone-telemetry", mock_data_telemetry)

        def test():
            data = self.conn.get_operational(
                "/openconfig-telemetry:telemetry-system/subscriptions/dynamic-subscriptions",
                strip=False,
            )
            expected = {
                "telemetry-system": {
                    "subscriptions": {
                        "dynamic-subscriptions": {
                            "dynamic-subscription": [
                                {
                                    "id": 4294967296 + 1,
                                    "state": {
                                        "id": 4294967296 + 1,
                                        "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                                        "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                                    },
                                    "sensor-paths": {
                                        "sensor-path": [
                                            {
                                                "path": "/test/path/one",
                                                "state": {
                                                    "path": "/test/path/one",
                                                },
                                            },
                                        ],
                                    },
                                },
                                {
                                    "id": 4294967296 + 2,
                                    "state": {
                                        "id": 4294967296 + 2,
                                        "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                                        "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
                                        "sample-interval": 5 * 1000 * 1000 * 1000,
                                        "heartbeat-interval": 60 * 1000 * 1000 * 1000,
                                        "suppress-redundant": True,
                                    },
                                    "sensor-paths": {
                                        "sensor-path": [
                                            {
                                                "path": "/test/path/two",
                                                "state": {
                                                    "path": "/test/path/two",
                                                },
                                            },
                                        ],
                                    },
                                },
                            ],
                        }
                    }
                }
            }
            self.assertEqual(data, expected)

        await self.run_xlate_test(test)


if __name__ == "__main__":
    unittest.main()
