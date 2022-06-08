"""Tests of gNMI server."""

# pylint: disable=W0212,C0103

import unittest
import time
import json
import grpc
import sysrepo
from tests.lib import MockRepository, gNMIServerTestCase
from goldstone.north.gnmi.server import (
    Request,
    GetRequest,
    SetRequest,
    UpdateRequest,
    DeleteRequest,
)
from goldstone.north.gnmi.proto import gnmi_pb2
from goldstone.north.gnmi.repo.repo import NotFoundError
from goldstone.north.gnmi.repo.sysrepo import Sysrepo


def append_path_element(path: gnmi_pb2.Path, name, key=None, val=None):
    if key is not None and val is not None:
        pe = gnmi_pb2.PathElem(name=name, key={key: val})
    else:
        pe = gnmi_pb2.PathElem(name=name)
    path.elem.append(pe)


class TestRequest(unittest.TestCase):
    """Test for Request."""

    def test_parse_xpath(self):
        prefix = gnmi_pb2.Path()
        path = gnmi_pb2.Path()
        pe = gnmi_pb2.PathElem(name="a", key={"b": "B", "c": "C"})
        path.elem.append(pe)
        append_path_element(path, "d")
        append_path_element(path, "e", "f", "F")
        expected = "/a[b='B'][c='C']/d/e[f='F']"
        request = Request("repo", prefix, path)
        self.assertEqual(request.repo, "repo")
        self.assertEqual(request.prefix, prefix)
        self.assertEqual(request.gnmi_path, path)
        self.assertEqual(request.xpath, expected)

    def test_parse_xpath_with_prefix(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "x")
        append_path_element(prefix, "y", "z", "Z")
        path = gnmi_pb2.Path()
        pe = gnmi_pb2.PathElem(name="a", key={"b": "B", "c": "C"})
        path.elem.append(pe)
        append_path_element(path, "d")
        append_path_element(path, "e", "f", "F")
        expected = "/x/y[z='Z']/a[b='B'][c='C']/d/e[f='F']"
        request = Request("repo", prefix, path)
        self.assertEqual(request.repo, "repo")
        self.assertEqual(request.prefix, prefix)
        self.assertEqual(request.gnmi_path, path)
        self.assertEqual(request.xpath, expected)


class TestGetRequest(unittest.TestCase):
    """Tests for GetRequest."""

    def test_get_request(self):
        data = {
            "components": {
                "component": [
                    {
                        "name": "c1",
                    }
                ]
            }
        }
        repo = MockRepository(data=data)
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "openconfig-platform:components")
        path = gnmi_pb2.Path()
        append_path_element(path, "component", "name", "c1")
        request = GetRequest(repo, prefix, path)
        expected_time_min = time.time_ns()
        request.exec()
        expected_time_max = time.time_ns()
        self.assertGreater(request.timestamp, expected_time_min)
        self.assertLess(request.timestamp, expected_time_max)
        self.assertDictEqual(request.result, {"name": "c1"})
        self.assertEqual(request.json_result(), '{"name": "c1"}')


class TestSetRequest(unittest.TestCase):
    """Tests for SetRequest."""

    def test_decode_val_json(self):
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        val = gnmi_pb2.TypedValue()
        val.json_val = b'{"a": {"b": "B", "c": ["C", "D", "E"]}}'
        expected = {"a": {"b": "B", "c": ["C", "D", "E"]}}
        actual = request._decode_val(val)
        self.assertEqual(actual, expected)
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.OK.value[0],
            message=None,
        )
        self.assertEqual(request.status, expected_status)

    def test_decode_val_ascii(self):
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        val = gnmi_pb2.TypedValue()
        ascii_val = '{"a": {"b": "B", "c": ["C", "D", "E"]}}'
        val.ascii_val = ascii_val
        actual = request._decode_val(val)
        self.assertIsNone(actual)
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.UNIMPLEMENTED.value[0],
            message="encoding ascii_val is not supported.",
        )
        self.assertEqual(request.status, expected_status)

    def test_is_container_list(self):
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        val = [1, 2, 3]
        actual = request._is_container_list(val)
        self.assertFalse(actual)
        val = [{"a": [1, 2, 3]}]
        actual = request._is_container_list(val)
        self.assertTrue(actual)

    def test_parse_val_into_leaves_with_a_leaf_value(self):
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        request.xpath = "/x/y/z"
        request.leaves = {}
        val = gnmi_pb2.TypedValue()
        val_src = "A"
        val.json_val = json.dumps(val_src).encode()
        request._parse_val_into_leaves(val)
        expected = {"/x/y/z": "A"}
        self.assertDictEqual(request.leaves, expected)

    def test_parse_val_into_leaves_with_a_leaf_list(self):
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        request.xpath = "/x/y/z"
        request.leaves = {}
        val = gnmi_pb2.TypedValue()
        val_src = ["A", "B", "C"]
        val.json_val = json.dumps(val_src).encode()
        request._parse_val_into_leaves(val)
        expected = {"/x/y/z": ["A", "B", "C"]}
        self.assertDictEqual(request.leaves, expected)

    def test_parse_val_into_leaves_with_a_dict_without_lists(self):
        # Dictionary which does not have any container lists.
        p = gnmi_pb2.Path()
        request = SetRequest(None, p, p)
        request.xpath = "/x/y/z"
        request.leaves = {}
        val = gnmi_pb2.TypedValue()
        val_src = {
            "V1": {
                "v1": {"v11": True, "v12": [1, 2, 3]},
                "v2": 1,
            },
            "V2": {
                "v1": {
                    "v11": False,
                    "v12": [0, 1, 2],
                },
                "v2": 0,
            },
            "V3": "str",
            "V4": ["v1", "v2", "v3"],
        }
        val.json_val = json.dumps(val_src).encode()
        request._parse_val_into_leaves(val)
        expected = {
            "/x/y/z/V1/v1/v11": True,
            "/x/y/z/V1/v1/v12": [1, 2, 3],
            "/x/y/z/V1/v2": 1,
            "/x/y/z/V2/v1/v11": False,
            "/x/y/z/V2/v1/v12": [0, 1, 2],
            "/x/y/z/V2/v2": 0,
            "/x/y/z/V3": "str",
            "/x/y/z/V4": ["v1", "v2", "v3"],
        }
        self.assertDictEqual(request.leaves, expected)

    def test_parse_val_into_leaves_with_a_container_lists(self):
        p = gnmi_pb2.Path()
        val = gnmi_pb2.TypedValue()
        val_src = [
            {
                "name": "eth0",
                "config": {
                    "name": "eth0",
                    "type": "iana-if-type:ethernetCsmacd",
                    "mtu": 1500,
                    "description": "client-port",
                    "enabled": True,
                },
            },
            {
                "name": "eth1",
                "config": {
                    "name": "eth1",
                    "type": "iana-if-type:ethernetCsmacd",
                    "mtu": 100000,
                    "description": "line-port",
                    "enabled": False,
                },
            },
        ]
        val.json_val = json.dumps(val_src).encode()
        with Sysrepo() as repo:
            repo.start()
            request = SetRequest(repo, p, p)
            request.leaves = {}
            request.xpath = "/openconfig-interfaces:interfaces/interface"
            request._parse_val_into_leaves(val)
            expected = {
                "/openconfig-interfaces:interfaces/interface[name='eth0']": None,
                "/openconfig-interfaces:interfaces/interface[name='eth0']/name": "eth0",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/name": "eth0",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/type": "iana-if-type:ethernetCsmacd",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/mtu": 1500,
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/description": "client-port",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/enabled": True,
                "/openconfig-interfaces:interfaces/interface[name='eth1']": None,
                "/openconfig-interfaces:interfaces/interface[name='eth1']/name": "eth1",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/name": "eth1",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/type": "iana-if-type:ethernetCsmacd",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/mtu": 100000,
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/description": "line-port",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/enabled": False,
            }
            self.assertDictEqual(request.leaves, expected)

    def test_parse_val_into_leaves_with_a_dict_has_a_container_list(self):
        # Dictionary which has a container lists.
        p = gnmi_pb2.Path()
        val = gnmi_pb2.TypedValue()
        val_src = {
            "interface": [
                {
                    "name": "eth0",
                    "config": {
                        "name": "eth0",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 1500,
                        "description": "client-port",
                        "enabled": True,
                    },
                },
                {
                    "name": "eth1",
                    "config": {
                        "name": "eth1",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 100000,
                        "description": "line-port",
                        "enabled": False,
                    },
                },
            ]
        }
        val.json_val = json.dumps(val_src).encode()
        with Sysrepo() as repo:
            repo.start()
            request = SetRequest(repo, p, p)
            request.leaves = {}
            request.xpath = "/openconfig-interfaces:interfaces"
            request._parse_val_into_leaves(val)
            expected = {
                "/openconfig-interfaces:interfaces/interface[name='eth0']": None,
                "/openconfig-interfaces:interfaces/interface[name='eth0']/name": "eth0",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/name": "eth0",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/type": "iana-if-type:ethernetCsmacd",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/mtu": 1500,
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/description": "client-port",
                "/openconfig-interfaces:interfaces/interface[name='eth0']/config/enabled": True,
                "/openconfig-interfaces:interfaces/interface[name='eth1']": None,
                "/openconfig-interfaces:interfaces/interface[name='eth1']/name": "eth1",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/name": "eth1",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/type": "iana-if-type:ethernetCsmacd",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/mtu": 100000,
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/description": "line-port",
                "/openconfig-interfaces:interfaces/interface[name='eth1']/config/enabled": False,
            }
            self.assertDictEqual(request.leaves, expected)

    def test_parse_val_into_leaves_with_leaves_have_references(self):
        # Container list which has references to other module.
        p = gnmi_pb2.Path()
        val = gnmi_pb2.TypedValue()
        val_src = {
            "component": [
                {
                    "name": "c1",
                    "config": {"name": "c1"},
                    "openconfig-platform-transceiver:transceiver": {
                        "physical-channels": {
                            "channel": [
                                {"index": 0, "config": {"index": 0}},
                                {"index": 1, "config": {"index": 1}},
                            ]
                        }
                    },
                },
                {
                    "name": "c2",
                    "config": {"name": "c2"},
                    "openconfig-platform-transceiver:transceiver": {
                        "physical-channels": {
                            "channel": [
                                {"index": 65534, "config": {"index": 65534}},
                                {"index": 65535, "config": {"index": 65535}},
                            ]
                        }
                    },
                },
            ]
        }
        val.json_val = json.dumps(val_src).encode()
        with Sysrepo() as repo:
            repo.start()
            request = SetRequest(repo, p, p)
            request.leaves = {}
            request.xpath = "/openconfig-platform:components"
            request._parse_val_into_leaves(val)
            expected = {
                "/openconfig-platform:components/component[name='c1']": None,
                "/openconfig-platform:components/component[name='c1']/name": "c1",
                "/openconfig-platform:components/component[name='c1']/config/name": "c1",
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='0']": None,
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='0']/index": 0,
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='0']/config/index": 0,
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='1']": None,
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='1']/index": 1,
                "/openconfig-platform:components/component[name='c1']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='1']/config/index": 1,
                "/openconfig-platform:components/component[name='c2']": None,
                "/openconfig-platform:components/component[name='c2']/name": "c2",
                "/openconfig-platform:components/component[name='c2']/config/name": "c2",
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65534']": None,
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65534']/index": 65534,
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65534']/config/index": 65534,
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65535']": None,
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65535']/index": 65535,
                "/openconfig-platform:components/component[name='c2']/openconfig-platform-transceiver:transceiver"
                "/physical-channels/channel[index='65535']/config/index": 65535,
            }
            self.assertDictEqual(request.leaves, expected)

    def test_create_leaves_to_set_with_an_invalid_container_list(self):
        p = gnmi_pb2.Path()
        val = gnmi_pb2.TypedValue()
        val_src = [
            {
                # Lack of "name" as key.
                "config": {
                    "name": "eth0",
                    "type": "iana-if-type:ethernetCsmacd",
                    "mtu": 1500,
                    "description": "client-port",
                    "enabled": True,
                },
            },
        ]
        val.json_val = json.dumps(val_src).encode()
        with Sysrepo() as repo:
            repo.start()
            request = SetRequest(repo, p, p)
            request.leaves = {}
            request.xpath = "/openconfig-interfaces:interfaces/interface"
            request._parse_val_into_leaves(val)
            expected_status_code = grpc.StatusCode.INVALID_ARGUMENT.value[0]
            self.assertEqual(request.status.code, expected_status_code)


class TestDeleteRequest(unittest.TestCase):
    """Tests for DeleteRequest."""

    def test_delete_request(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "openconfig-platform:components")
        path = gnmi_pb2.Path()
        append_path_element(path, "component", "name", "c1")
        repo = MockRepository()
        request = DeleteRequest(repo, prefix, path)
        self.assertEqual(
            request.xpath,
            "/openconfig-platform:components/component[name='c1']",
        )
        self.assertEqual(request.operation, gnmi_pb2.UpdateResult.Operation.DELETE)
        request.exec()
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.OK.value[0],
            message=None,
        )
        self.assertEqual(request.status, expected_status)

    def test_delete_request_not_found_error(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "openconfig-platform:components")
        path = gnmi_pb2.Path()
        append_path_element(path, "component", "name", "c1")
        repo = MockRepository(exception=NotFoundError("For testing."))
        request = DeleteRequest(repo, prefix, path)
        self.assertEqual(
            request.xpath,
            "/openconfig-platform:components/component[name='c1']",
        )
        self.assertEqual(request.operation, gnmi_pb2.UpdateResult.Operation.DELETE)
        request.exec()
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.OK.value[0],
            message=None,
        )
        self.assertEqual(request.status, expected_status)

    def test_delete_request_invalid_argument_error(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "aaa:bbb")
        path = gnmi_pb2.Path()
        append_path_element(path, "ccc", "ddd", "eee")
        append_path_element(path, "fff")
        repo = MockRepository(exception=Exception("For testing."))
        request = DeleteRequest(repo, prefix, path)
        self.assertEqual(request.xpath, "/aaa:bbb/ccc[ddd='eee']/fff")
        self.assertEqual(request.operation, gnmi_pb2.UpdateResult.Operation.DELETE)
        request.exec()
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.UNKNOWN.value[0],
            message="failed to delete. xpath: /aaa:bbb/ccc[ddd='eee']/fff. For testing.",
        )
        self.assertEqual(request.status, expected_status)


class TestUpdateRequest(unittest.TestCase):
    """Tests for UpdateRequest."""

    def test_update_request(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "openconfig-platform:components")
        path = gnmi_pb2.Path()
        append_path_element(path, "component", "name", "c1")
        val = gnmi_pb2.TypedValue()
        val_src = {"name": "c1", "config": {"name": "c1"}}
        val.json_val = json.dumps(val_src).encode()
        repo = MockRepository()
        request = UpdateRequest(repo, prefix, path, val)
        self.assertEqual(
            request.xpath,
            "/openconfig-platform:components/component[name='c1']",
        )
        expected_leaves = {
            "/openconfig-platform:components/component[name='c1']/name": "c1",
            "/openconfig-platform:components/component[name='c1']/config/name": "c1",
        }
        self.assertDictEqual(request.leaves, expected_leaves)
        self.assertEqual(request.operation, gnmi_pb2.UpdateResult.Operation.UPDATE)
        request.exec()
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.OK.value[0],
            message=None,
        )
        self.assertEqual(request.status, expected_status)

    def test_update_request_invalid_argument_error(self):
        prefix = gnmi_pb2.Path()
        append_path_element(prefix, "aaa:bbb")
        path = gnmi_pb2.Path()
        append_path_element(path, "ccc", "ddd", "eee")
        append_path_element(path, "fff")
        val = gnmi_pb2.TypedValue()
        val_src = "ggg"
        val.json_val = json.dumps(val_src).encode()
        repo = MockRepository(exception=Exception("For testing."))
        request = UpdateRequest(repo, prefix, path, val)
        self.assertEqual(request.xpath, "/aaa:bbb/ccc[ddd='eee']/fff")
        self.assertEqual(request.operation, gnmi_pb2.UpdateResult.Operation.UPDATE)
        expected_leaves = {"/aaa:bbb/ccc[ddd='eee']/fff": "ggg"}
        self.assertDictEqual(request.leaves, expected_leaves)
        request.exec()
        expected_status = gnmi_pb2.Error(
            code=grpc.StatusCode.UNKNOWN.value[0],
            message="failed to update. xpath: /aaa:bbb/ccc[ddd='eee']/fff, value: ggg. For testing.",
        )
        self.assertEqual(request.status, expected_status)


class TestCapabilities(gNMIServerTestCase):
    """Tests for gNMI Capabilities service."""

    MOCK_MODULES = []

    def test_capabilities(self):
        expected = {
            "supported_models": [
                {
                    "name": "openconfig-interfaces",
                    "organization": "OpenConfig working group",
                    "version": "2021-04-06",
                },
                {
                    "name": "openconfig-if-ethernet",
                    "organization": "OpenConfig working group",
                    "version": "2021-07-07",
                },
                {
                    "name": "openconfig-platform",
                    "organization": "OpenConfig working group",
                    "version": "2021-01-18",
                },
                {
                    "name": "openconfig-platform-types",
                    "organization": "OpenConfig working group",
                    "version": "2021-01-18",
                },
                {
                    "name": "openconfig-platform-port",
                    "organization": "OpenConfig working group",
                    "version": "2021-06-16",
                },
                {
                    "name": "openconfig-platform-transceiver",
                    "organization": "OpenConfig working group",
                    "version": "2021-02-23",
                },
                {
                    "name": "openconfig-platform-fan",
                    "organization": "OpenConfig working group",
                    "version": "2018-11-21",
                },
                {
                    "name": "openconfig-platform-psu",
                    "organization": "OpenConfig working group",
                    "version": "2018-11-21",
                },
                {
                    "name": "openconfig-terminal-device",
                    "organization": "OpenConfig working group",
                    "version": "2021-02-23",
                },
                {
                    "name": "openconfig-transport-line-common",
                    "organization": "OpenConfig working group",
                    "version": "2019-06-03",
                },
                {
                    "name": "openconfig-transport-types",
                    "organization": "OpenConfig working group",
                    "version": "2021-03-22",
                },
                {
                    "name": "openconfig-types",
                    "organization": "OpenConfig working group",
                    "version": "2019-04-16",
                },
                {
                    "name": "openconfig-yang-types",
                    "organization": "OpenConfig working group",
                    "version": "2021-03-02",
                },
                {
                    "name": "openconfig-telemetry",
                    "organization": "OpenConfig working group",
                    "version": "2018-11-21",
                },
                {
                    "name": "openconfig-telemetry-types",
                    "organization": "OpenConfig working group",
                    "version": "2018-11-21",
                },
            ],
            "supported_encodings": [gnmi_pb2.Encoding.JSON],
            "gNMI_version": "0.6.0",
        }
        request = gnmi_pb2.CapabilityRequest()
        actual, code = self.gnmi_capabilities(request)
        self.assertEqual(code, grpc.StatusCode.OK)

        act_models = actual.supported_models
        exp_models = expected.get("supported_models")
        self.assertEqual(len(act_models), len(exp_models))
        for act, exp in zip(act_models, exp_models):
            self.assertEqual(act.name, exp.get("name"))
            self.assertEqual(act.organization, exp.get("organization"))
            self.assertEqual(act.version, exp.get("version"))
        self.assertEqual(
            actual.supported_encodings, expected.get("supported_encodings")
        )
        self.assertEqual(actual.gNMI_version, expected.get("gNMI_version"))


class TestGet(gNMIServerTestCase):
    """Tests gNMI server Get Service."""

    MOCK_MODULES = [
        "openconfig-terminal-device",
        "openconfig-platform",
        "openconfig-interfaces",
    ]
    mock_data = {
        "openconfig-terminal-device:terminal-device": {
            "logical-channels": {
                "channel": [
                    {
                        "index": 1,
                        "state": {
                            "index": 1,
                            "description": "description for channel#1",
                            "test-signal": True,
                            "link-state": "UP",
                        },
                        "ingress": {
                            "state": {
                                "transceiver": "port1",
                                "physical-channel": [
                                    0,
                                    10,
                                    100,
                                    1000,
                                ],
                            }
                        },
                    },
                    {
                        "index": 2,
                        "state": {
                            "index": 2,
                            "description": "description for channel#2",
                            "test-signal": False,
                            "link-state": "DOWN",
                        },
                        "ingress": {
                            "state": {
                                "transceiver": "port2",
                                "physical-channel": [
                                    1,
                                    11,
                                    111,
                                    1111,
                                ],
                            }
                        },
                    },
                ]
            }
        }
    }

    async def test_get_a_leaf(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "1")
            append_path_element(path, "state")
            append_path_element(path, "index")
            request = gnmi_pb2.GetRequest(path=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = 1
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_a_leaf_slash_in_key(self):
        mock_data = {
            "interfaces": {
                "interface": [
                    {
                        "ethernet": {
                            "state": {"fec-mode": "openconfig-if-ethernet:FEC_RS528"}
                        },
                        "name": "Interface1/0/1",
                        "state": {
                            "admin-status": "UP",
                            "enabled": True,
                            "hardware-port": "client-port1",
                            "mtu": 10000,
                            "name": "Interface1/0/1",
                            "oper-status": "DOWN",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    },
                    {
                        "ethernet": {
                            "state": {"fec-mode": "openconfig-if-ethernet:FEC_RS528"}
                        },
                        "name": "Interface1/1/1",
                        "state": {
                            "admin-status": "UP",
                            "enabled": True,
                            "mtu": 10000,
                            "name": "Interface1/1/1",
                            "oper-status": "DOWN",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    },
                ]
            }
        }
        self.set_mock_oper_data("openconfig-interfaces", mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            request = gnmi_pb2.GetRequest(path=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = True
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_a_leaf_with_JSON_encoding(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "1")
            append_path_element(path, "state")
            append_path_element(path, "index")
            request = gnmi_pb2.GetRequest(path=[path], encoding=gnmi_pb2.Encoding.JSON)
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = 1
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_a_leaf_list(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "1")
            append_path_element(path, "ingress")
            append_path_element(path, "state")
            append_path_element(path, "physical-channel")
            request = gnmi_pb2.GetRequest(path=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [0, 10, 100, 1000]
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_a_container(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "1")
            append_path_element(path, "state")
            request = gnmi_pb2.GetRequest(path=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "index": 1,
                "description": "description for channel#1",
                "test-signal": True,
                "link-state": "UP",
            }
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_a_container_list(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel")
            request = gnmi_pb2.GetRequest(path=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)
            self.assertGreater(actual.notification[0].timestamp, expected_time_min)
            self.assertLess(actual.notification[0].timestamp, expected_time_max)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {
                    "index": 1,
                    "state": {
                        "index": 1,
                        "description": "description for channel#1",
                        "test-signal": True,
                        "link-state": "UP",
                    },
                    "ingress": {
                        "state": {
                            "transceiver": "port1",
                            "physical-channel": [
                                0,
                                10,
                                100,
                                1000,
                            ],
                        }
                    },
                },
                {
                    "index": 2,
                    "state": {
                        "index": 2,
                        "description": "description for channel#2",
                        "test-signal": False,
                        "link-state": "DOWN",
                    },
                    "ingress": {
                        "state": {
                            "transceiver": "port2",
                            "physical-channel": [
                                1,
                                11,
                                111,
                                1111,
                            ],
                        }
                    },
                },
            ]
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_multiple_node_with_prefix(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-terminal-device:terminal-device")
            append_path_element(prefix, "logical-channels")
            append_path_element(prefix, "channel", "index", "2")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "state")
            append_path_element(path1, "index")
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "state")
            append_path_element(path2, "description")
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "state")
            append_path_element(path3, "test-signal")
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "state")
            append_path_element(path4, "link-state")
            path5 = gnmi_pb2.Path()
            append_path_element(path5, "ingress")
            paths = [path1, path2, path3, path4, path5]
            request = gnmi_pb2.GetRequest(prefix=prefix, path=paths)
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(len(actual.notification), len(paths))
            expected = [
                2,
                "description for channel#2",
                False,
                "DOWN",
                {
                    "state": {
                        "transceiver": "port2",
                        "physical-channel": [1, 11, 111, 1111],
                    }
                },
            ]
            for n, p, e in zip(actual.notification, paths, expected):
                self.assertEqual(n.prefix, prefix)
                self.assertGreater(n.timestamp, expected_time_min)
                self.assertLess(n.timestamp, expected_time_max)
                self.assertEqual(n.update[0].path, p)
                a = json.loads(n.update[0].val.json_val.decode("utf-8"))
                self.assertEqual(a, e)

        await self.run_gnmi_server_test(test)

    async def test_get_leaves_without_key(self):
        self.set_mock_oper_data("openconfig-terminal-device", self.mock_data)

        def test():
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-terminal-device:terminal-device")
            append_path_element(prefix, "logical-channels")
            append_path_element(prefix, "channel")
            append_path_element(prefix, "state")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "index")
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "description")
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "test-signal")
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "link-state")
            paths = [path1, path2, path3, path4]
            request = gnmi_pb2.GetRequest(prefix=prefix, path=paths)
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_get(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(len(actual.notification), len(paths))
            expected = [
                [1, 2],
                ["description for channel#1", "description for channel#2"],
                [True, False],
                ["UP", "DOWN"],
            ]
            for n, p, e in zip(actual.notification, paths, expected):
                self.assertEqual(n.prefix, prefix)
                self.assertGreater(n.timestamp, expected_time_min)
                self.assertLess(n.timestamp, expected_time_max)
                self.assertEqual(n.update[0].path, p)
                a = json.loads(n.update[0].val.json_val.decode("utf-8"))
                self.assertEqual(a, e)

        await self.run_gnmi_server_test(test)

    async def test_get_a_leaf_path_includes_namespace_prefix(self):
        mock_data = {
            "openconfig-platform:components": {
                "component": [
                    {
                        "name": "c1",
                        "state": {"name": "c1"},
                        "openconfig-platform-transceiver:transceiver": {
                            "physical-channels": {
                                "channel": [
                                    {"index": 0, "state": {"index": 0}},
                                    {"index": 65535, "state": {"index": 65535}},
                                ]
                            }
                        },
                    }
                ]
            }
        }
        self.set_mock_oper_data("openconfig-platform", mock_data)

        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            # Namespace prefix "openconfig-platform-transceiver:".
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            append_path_element(path, "physical-channels")
            append_path_element(path, "channel")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, path)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {"index": 0, "state": {"index": 0}},
                {"index": 65535, "state": {"index": 65535}},
            ]
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_get_not_found(self):
        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "blah")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)
            self.assertEqual(actual.error.code, grpc.StatusCode.NOT_FOUND.value[0])

        await self.run_gnmi_server_test(test)

    async def test_get_unsupported_path(self):
        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "blah")
            append_path_element(path, "blah")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.INVALID_ARGUMENT)
            self.assertEqual(
                actual.error.code, grpc.StatusCode.INVALID_ARGUMENT.value[0]
            )

        await self.run_gnmi_server_test(test)

    async def test_get_unimplemented_encoding(self):
        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            for e in gnmi_pb2.Encoding.keys():
                if e == "JSON":
                    continue
                request = gnmi_pb2.GetRequest(path=[path], encoding=e)
                actual, code = self.gnmi_get(request)
                self.assertEqual(code, grpc.StatusCode.UNIMPLEMENTED)
                self.assertEqual(
                    actual.error.code, grpc.StatusCode.UNIMPLEMENTED.value[0]
                )

        await self.run_gnmi_server_test(test)


class TestSet(gNMIServerTestCase):
    """Tests for gNMI server Set service."""

    # NOTE: Do not change this MOCK_MODULES order. "asyncSetUp()" removes all
    #   configurations for each module in this order. "openconfig-platform"
    #   configurations should be removed after "openconfig-terminal-device"
    #   ones. Because, a "openconfig-terminal-device" configuration has a
    #   reference to a "openconfig-platform" one. If you remove
    #   "openconfig-platform" configurations first, you get a reference error.
    MOCK_MODULES = [
        "openconfig-interfaces",
        "openconfig-terminal-device",
        "openconfig-platform",
    ]

    async def test_set_a_leaf(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            target_path = gnmi_pb2.Path()
            append_path_element(target_path, "openconfig-interfaces:interfaces")
            append_path_element(target_path, "interface", "name", "Ethernet1")
            append_path_element(target_path, "config")
            append_path_element(target_path, "enabled")

            # Check "enabled" is True.
            request = gnmi_pb2.GetRequest(path=[target_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_enabled = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            self.assertTrue(actual_enabled)

            # Set a leaf. Update "enabled" to False.
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(False).encode()
            update = gnmi_pb2.Update(path=target_path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check "enabled" is False.
            request = gnmi_pb2.GetRequest(path=[target_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_enabled = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            self.assertFalse(actual_enabled)

            # Delete a leaf. Delete "enabled".
            request = gnmi_pb2.SetRequest(delete=[target_path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.DELETE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check "enabled" was deleted.
            request = gnmi_pb2.GetRequest(path=[target_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

        await self.run_gnmi_server_test(test)

    async def test_set_a_container(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Update a container.
            update_path = gnmi_pb2.Path()
            append_path_element(update_path, "openconfig-interfaces:interfaces")
            append_path_element(update_path, "interface", "name", "Ethernet1")
            append_path_element(update_path, "config")
            set_data = {
                "mtu": 1500,
                "description": "This is Ethernet1.",
                "enabled": False,
            }
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(set_data).encode()
            update = gnmi_pb2.Update(path=update_path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check updated.
            request = gnmi_pb2.GetRequest(path=[update_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "mtu": 1500,
                "description": "This is Ethernet1.",
                "enabled": False,
            }
            self.assertEqual(act, expected)

            # Delete a container.
            delete_path = gnmi_pb2.Path()
            append_path_element(delete_path, "openconfig-interfaces:interfaces")
            append_path_element(delete_path, "interface", "name", "Ethernet1")
            request = gnmi_pb2.SetRequest(delete=[delete_path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.DELETE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check deleted.
            request = gnmi_pb2.GetRequest(path=[delete_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

        await self.run_gnmi_server_test(test)

    async def test_set_multiple_nodes(self):
        def test():
            # Multiple updates in a request.
            config_data = [
                {
                    "name": "Ethernet1",
                    "config": {
                        "name": "Ethernet1",
                        "type": "iana-if-type:ethernetCsmacd",
                    },
                }
            ]
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-interfaces:interfaces")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "interface")
            val1 = gnmi_pb2.TypedValue()
            val1.json_val = json.dumps(config_data).encode()
            update1 = gnmi_pb2.Update(path=path1, val=val1)
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "interface", "name", "Ethernet1")
            append_path_element(path2, "config")
            append_path_element(path2, "mtu")
            val2 = gnmi_pb2.TypedValue()
            val2.json_val = json.dumps(1500).encode()
            update2 = gnmi_pb2.Update(path=path2, val=val2)
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "interface", "name", "Ethernet1")
            append_path_element(path3, "config")
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps({"enabled": True}).encode()
            update3 = gnmi_pb2.Update(path=path3, val=val3)
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "interface", "name", "Ethernet1")
            append_path_element(path4, "config")
            append_path_element(path4, "loopback-mode")
            val4 = gnmi_pb2.TypedValue()
            val4.json_val = json.dumps(False).encode()
            update4 = gnmi_pb2.Update(path=path4, val=val4)
            update = [update1, update2, update3, update4]
            request = gnmi_pb2.SetRequest(prefix=prefix, update=update)
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.prefix, prefix)
            self.assertEqual(len(actual.response), len(update))
            for r, u in zip(actual.response, update):
                self.assertEqual(r.message.code, grpc.StatusCode.OK.value[0])
                self.assertEqual(r.op, gnmi_pb2.UpdateResult.Operation.UPDATE)
                self.assertEqual(r.path, u.path)
                self.assertGreater(r.timestamp, expected_time_min)
                self.assertLess(r.timestamp, expected_time_max)

            # Check updated.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "config": {
                    "name": "Ethernet1",
                    "type": "iana-if-type:ethernetCsmacd",
                    "mtu": 1500,
                    "enabled": True,
                    "loopback-mode": False,
                },
            }
            self.assertEqual(act, expected)

            # Deletes and updates in a request.
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-interfaces:interfaces")
            append_path_element(prefix, "interface", "name", "Ethernet1")
            append_path_element(prefix, "config")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "mtu")
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "loopback-mode")
            delete = [path1, path2]
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "description")
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps("This is Ethernet1.").encode()
            update3 = gnmi_pb2.Update(path=path3, val=val3)
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "enabled")
            val4 = gnmi_pb2.TypedValue()
            val4.json_val = json.dumps(False).encode()
            val5 = gnmi_pb2.TypedValue()
            val5.json_val = json.dumps(True).encode()
            update4 = gnmi_pb2.Update(path=path4, val=val4)
            update5 = gnmi_pb2.Update(path=path4, val=val5)
            # NOTE: Two updates which set different values to same path should
            #       be success as per gnmi-specification 3.4 but couldn't due
            #       to the sysrepo limitation so specify same value instead.
            # update = [update3, update4, update5]
            update = [update3, update4, update4]
            request = gnmi_pb2.SetRequest(prefix=prefix, delete=delete, update=update)
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.prefix, prefix)
            expected_path = [path1, path2, path3, path4, path4]
            expected_op = [
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
            ]
            self.assertEqual(len(actual.response), len(delete) + len(update))
            for r, p, o in zip(actual.response, expected_path, expected_op):
                self.assertEqual(r.path, p)
                self.assertEqual(r.op, o)
                self.assertEqual(r.message.code, grpc.StatusCode.OK.value[0])

            # Check deleted and updated.
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-interfaces:interfaces")
            append_path_element(prefix, "interface", "name", "Ethernet1")
            path = gnmi_pb2.Path()
            append_path_element(path, "config")
            paths = [path]
            request = gnmi_pb2.GetRequest(prefix=prefix, path=paths)
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].prefix, prefix)
            self.assertEqual(actual.notification[0].update[0].path, path)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": False,
                "description": "This is Ethernet1.",
            }
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_set_a_leaf_path_includes_namespace_prefix(self):
        def test():
            config_data = {
                "component": [
                    {
                        "name": "c1",
                        "config": {"name": "c1"},
                        # Namespace prefix ""openconfig-platform-transceiver:".
                        "openconfig-platform-transceiver:transceiver": {
                            # NOTE: module-functional-type should be unnecessary in this configuration set. But without
                            #   it, sysrepo raises a validation failed error like below;
                            #   > When condition "../../../config/module-functional-type =
                            #   > 'oc-opt-types:TYPE_STANDARD_OPTIC'" not satisfied.
                            "config": {
                                "module-functional-type": "openconfig-transport-types:TYPE_STANDARD_OPTIC",
                            },
                            "physical-channels": {
                                "channel": [
                                    {"index": 0, "config": {"index": 0}},
                                    {"index": 65535, "config": {"index": 65535}},
                                ]
                            },
                        },
                    }
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

            # Check updated.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            append_path_element(path, "physical-channels")
            append_path_element(path, "channel")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {"index": 0, "config": {"index": 0}},
                {"index": 65535, "config": {"index": 65535}},
            ]
            self.assertEqual(act, expected)

            # Delete.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            append_path_element(path, "physical-channels")
            append_path_element(path, "channel", "index", "0")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

            # Check deleted.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            append_path_element(path, "physical-channels")
            append_path_element(path, "channel")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {"index": 65535, "config": {"index": 65535}},
            ]
            self.assertEqual(act, expected)

            # Delete the node that has a namespace prefix.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

            # Check deleted.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            append_path_element(path, "component", "name", "c1")
            append_path_element(path, "openconfig-platform-transceiver:transceiver")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

        await self.run_gnmi_server_test(test)

    async def test_set_a_container_list(self):
        def test():
            # Update a list of containers.
            config_data = [
                {
                    "name": "Ethernet1",
                    "config": {
                        "name": "Ethernet1",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 1500,
                        "description": "This is Ethernet1.",
                        "enabled": True,
                    },
                },
                {
                    "name": "Ethernet2",
                    "config": {
                        "name": "Ethernet2",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 1480,
                        "description": "This is Ethernet2.",
                        "enabled": False,
                    },
                },
            ]
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check updated.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {
                    "name": "Ethernet1",
                    "config": {
                        "name": "Ethernet1",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 1500,
                        "description": "This is Ethernet1.",
                        "enabled": True,
                    },
                },
                {
                    "name": "Ethernet2",
                    "config": {
                        "name": "Ethernet2",
                        "type": "iana-if-type:ethernetCsmacd",
                        "mtu": 1480,
                        "description": "This is Ethernet2.",
                        "enabled": False,
                    },
                },
            ]
            self.assertEqual(act, expected)

            # Delete an entry of the list.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            request = gnmi_pb2.SetRequest(delete=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.DELETE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check deleted.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

            # Delete a list of containers
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            request = gnmi_pb2.SetRequest(delete=[path])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.DELETE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check deleted.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

        await self.run_gnmi_server_test(test)

    async def test_set_a_leaf_list(self):
        def test():
            # Prepare physical-channels.
            physical_channels_data = {
                "component": [
                    {
                        "name": "c1",
                        "config": {"name": "c1"},
                        "openconfig-platform-transceiver:transceiver": {
                            # NOTE: module-functional-type should be unnecessary in this configuration set. But without
                            #   it, sysrepo raises a validation failed error like below;
                            #   > When condition "../../../config/module-functional-type =
                            #   > 'oc-opt-types:TYPE_STANDARD_OPTIC'" not satisfied.
                            "config": {
                                "module-functional-type": "openconfig-transport-types:TYPE_STANDARD_OPTIC",
                            },
                            "physical-channels": {
                                "channel": [
                                    {"index": 0, "config": {"index": 0}},
                                    {"index": 10, "config": {"index": 10}},
                                    {"index": 100, "config": {"index": 100}},
                                    {"index": 65535, "config": {"index": 65535}},
                                ]
                            },
                        },
                    }
                ]
            }
            path_pc = gnmi_pb2.Path()
            append_path_element(path_pc, "openconfig-platform:components")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(physical_channels_data).encode()
            update_pc = gnmi_pb2.Update(path=path_pc, val=val)

            # Prepare logical-channels.
            logical_channels_data = {
                "channel": [{"index": 99, "config": {"index": 99}}]
            }
            path_lc = gnmi_pb2.Path()
            append_path_element(path_lc, "openconfig-terminal-device:terminal-device")
            append_path_element(path_lc, "logical-channels")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(logical_channels_data).encode()
            update_lc = gnmi_pb2.Update(path=path_lc, val=val)

            # Set physical-channels and logical-channels.
            request = gnmi_pb2.SetRequest(update=[update_pc, update_lc])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

            # Add a leaf-list to ingress of logical-channel.
            config_data = [0, 65535]
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "99")
            append_path_element(path, "ingress")
            append_path_element(path, "config")
            append_path_element(path, "physical-channel")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check updated.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [0, 65535]
            self.assertListEqual(sorted(act), sorted(expected))

            # Add values to a leaf-list.
            config_data = [0, 10, 100]
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "99")
            append_path_element(path, "ingress")
            append_path_element(path, "config")
            append_path_element(path, "physical-channel")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Chech updated.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [0, 10, 100, 65535]
            self.assertListEqual(sorted(act), sorted(expected))

            # Delete a leaf-list.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "99")
            append_path_element(path, "ingress")
            append_path_element(path, "config")
            append_path_element(path, "physical-channel")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.DELETE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check deleted.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.NOT_FOUND)

        await self.run_gnmi_server_test(test)

    async def test_set_list_in_list(self):
        def test():
            # Prepare physical-channels.
            physical_channels_data = {
                "component": [
                    {
                        "name": "c1",
                        "config": {"name": "c1"},
                        "openconfig-platform-transceiver:transceiver": {
                            # NOTE: module-functional-type should be unnecessary in this configuration set. But without
                            #   it, sysrepo raises a validation failed error like below;
                            #   > When condition "../../../config/module-functional-type =
                            #   > 'oc-opt-types:TYPE_STANDARD_OPTIC'" not satisfied.
                            "config": {
                                "module-functional-type": "openconfig-transport-types:TYPE_STANDARD_OPTIC",
                            },
                            "physical-channels": {
                                "channel": [
                                    {"index": 0, "config": {"index": 0}},
                                    {"index": 1, "config": {"index": 1}},
                                    {"index": 10, "config": {"index": 10}},
                                    {"index": 100, "config": {"index": 100}},
                                    {"index": 1000, "config": {"index": 1000}},
                                    {"index": 10000, "config": {"index": 10000}},
                                    {"index": 60000, "config": {"index": 60000}},
                                    {"index": 65535, "config": {"index": 65535}},
                                ]
                            },
                        },
                    }
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-platform:components")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(physical_channels_data).encode()
            update_pc = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update_pc])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

            target_path = gnmi_pb2.Path()
            append_path_element(
                target_path, "openconfig-terminal-device:terminal-device"
            )
            append_path_element(target_path, "logical-channels")
            append_path_element(target_path, "channel")

            # Update a list of containers that have a leaf-list.
            config_data = [
                {
                    "index": 99,
                    "config": {"index": 99},
                    "ingress": {"config": {"physical-channel": [0, 10, 100]}},
                },
                {
                    "index": 999,
                    "config": {"index": 999},
                    "ingress": {"config": {"physical-channel": [1, 1000, 10000]}},
                },
            ]
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=target_path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check updated.
            request = gnmi_pb2.GetRequest(path=[target_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, target_path)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {
                    "index": 99,
                    "config": {"index": 99},
                    "ingress": {"config": {"physical-channel": [0, 10, 100]}},
                },
                {
                    "index": 999,
                    "config": {"index": 999},
                    "ingress": {"config": {"physical-channel": [1, 1000, 10000]}},
                },
            ]
            self.assertEqual(act, expected)

            # Update
            config_data = [
                {
                    "index": 99,
                    "ingress": {"config": {"physical-channel": [65535]}},
                },
                {
                    "index": 999,
                    "ingress": {"config": {"physical-channel": [60000]}},
                },
            ]
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=target_path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            expected_time_min = time.time_ns()
            actual, code = self.gnmi_set(request)
            expected_time_max = time.time_ns()
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            self.assertGreater(actual.timestamp, expected_time_min)
            self.assertLess(actual.timestamp, expected_time_max)
            self.assertGreater(actual.response[0].timestamp, expected_time_min)
            self.assertLess(actual.response[0].timestamp, expected_time_max)
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code, grpc.StatusCode.OK.value[0]
            )

            # Check updated.
            request = gnmi_pb2.GetRequest(path=[target_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.error.code, grpc.StatusCode.OK.value[0])
            self.assertEqual(actual.notification[0].update[0].path, target_path)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = [
                {
                    "index": 99,
                    "config": {"index": 99},
                    "ingress": {"config": {"physical-channel": [0, 10, 100, 65535]}},
                },
                {
                    "index": 999,
                    "config": {"index": 999},
                    "ingress": {
                        "config": {"physical-channel": [1, 1000, 10000, 60000]}
                    },
                },
            ]
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_empty_set_request(self):
        def test():
            request = gnmi_pb2.SetRequest()
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])

        await self.run_gnmi_server_test(test)

    async def test_update_with_unsupported_value_type(self):
        def test():
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    }
                ]
            }

            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            # ASCII is not supported yet.
            val.ascii_val = json.dumps(config_data)
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code,
                grpc.StatusCode.UNIMPLEMENTED.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_key_value(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Update key value.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "name")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps("eth1").encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

            # Check not updated.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_name = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = "Ethernet1"
            self.assertEqual(actual_name, expected)

        await self.run_gnmi_server_test(test)

    async def test_delete_key_value(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Delete key value.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "name")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

            # Check not deleted.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_interface = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "config": {
                    "name": "Ethernet1",
                    "type": "iana-if-type:ethernetCsmacd",
                    "enabled": True,
                },
            }
            self.assertEqual(actual_interface, expected)

        await self.run_gnmi_server_test(test)

    async def test_update_a_leaf_in_entry_not_exist(self):
        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "config")
            append_path_element(path, "description")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps("This is Ethernet1").encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            # TODO: In this case, code should be set to NOT_FOUND. But the
            #   error cannot be detected properly.
            # self.assertEqual(resp.message.code, grpc.StatusCode.NOT_FOUND.value[0])
            self.assertEqual(resp.message.code, grpc.StatusCode.ABORTED.value[0])

        await self.run_gnmi_server_test(test)

    async def test_delete_a_leaf_in_entry_not_exist(self):
        def test():
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "config")
            append_path_element(path, "description")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(resp.message.code, grpc.StatusCode.OK.value[0])

        await self.run_gnmi_server_test(test)

    async def test_update_an_unsupported_path(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Update unsupported path.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "config")
            # Unsupported (unknown) node "blah".
            append_path_element(path, "blah")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps("blah blah.").encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                # TODO: In this case, code should be set to INVALID_ARGUMENT.
                #   But the error cannot be detected properly.
                # grpc.StatusCode.INVALID_ARGUMENT.value[0]
                grpc.StatusCode.UNKNOWN.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_delete_an_unsupported_path(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Delete unsupported path.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "config")
            # Unsupported (unknown) node "blah".
            append_path_element(path, "blah")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code, grpc.StatusCode.INVALID_ARGUMENT.value[0]
            )

        await self.run_gnmi_server_test(test)

    async def test_update_a_read_only_leaf(self):
        def test():
            mock_data = {
                "openconfig-interfaces:interfaces": {
                    "interface": [
                        {
                            "name": "Ethernet1",
                            "state": {
                                "name": "Ethernet1",
                                "type": "iana-if-type:ethernetCsmacd",
                                "enabled": True,
                            },
                        },
                    ]
                }
            }
            self.set_mock_oper_data("openconfig-interfaces", mock_data)

            # Update a read-only leaf node.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(False).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            # TODO: In this case, code should be set to INVALID_ARGUMENT. But
            #   the error cannot be detected properly.
            # self.assertEqual(resp.message.code, grpc.StatusCode.INVALID_ARGUMENT.value[0])
            self.assertEqual(resp.message.code, grpc.StatusCode.ABORTED.value[0])

        await self.run_gnmi_server_test(test)

    async def test_delete_a_read_only_leaf(self):
        def test():
            mock_data = {
                "openconfig-interfaces:interfaces": {
                    "interface": [
                        {
                            "name": "Ethernet1",
                            "state": {
                                "name": "Ethernet1",
                                "type": "iana-if-type:ethernetCsmacd",
                                "enabled": True,
                            },
                        },
                    ]
                }
            }
            self.set_mock_oper_data("openconfig-interfaces", mock_data)

            # Delete a read-only leaf node.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Ethernet1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            # TODO: In this case, code and actual.message.code should be set
            #   to ABORTED and resp.message.code to INVALID_ARGUMENT. But the
            #   error cannot be detected and this leaf is not deleted actually.
            # self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(code, grpc.StatusCode.OK)
            # self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(actual.message.code, grpc.StatusCode.OK.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            # self.assertEqual(resp.message.code, grpc.StatusCode.INVALID_ARGUMENT.value[0])
            self.assertEqual(resp.message.code, grpc.StatusCode.OK.value[0])

            # Check not deleted.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_enabled = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            self.assertTrue(actual_enabled)

        await self.run_gnmi_server_test(test)

    async def test_update_without_key_in_path(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Update "enabled" without key.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            append_path_element(path, "config")
            append_path_element(path, "enabled")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(False).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_delete_without_key_in_path(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # delete "enabled" without key.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            append_path_element(path, "config")
            append_path_element(path, "enabled")
            request = gnmi_pb2.SetRequest(delete=[path])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

            # Check not deleted.
            request = gnmi_pb2.GetRequest(path=[path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            actual_enabled = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            self.assertTrue(actual_enabled)

        await self.run_gnmi_server_test(test)

    async def test_update_without_key_in_value(self):
        def test():
            config_data = {
                "interface": [
                    {
                        # Lack of "name" as key.
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_without_required_element(self):
        def test():
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "enabled": True,
                            # Required element "type" is not specified.
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            resp = actual.response[0]
            self.assertEqual(resp.path, path)
            self.assertEqual(
                resp.message.code,
                # TODO: In this case, code should be set to INVALID_ARGUMENT.
                #   But the error cannot be detected properly.
                # grpc.StatusCode.INVALID_ARGUMENT.value[0]
                grpc.StatusCode.ABORTED.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_with_invalid_arg_name(self):
        def test():
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            # Leaf "typo" does not exist in this schema.
                            "typo": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code,
                # TODO: In this case, code should be set to INVALID_ARGUMENT.
                #   But the error cannot be detected properly.
                # grpc.StatusCode.INVALID_ARGUMENT.value[0]
                grpc.StatusCode.UNKNOWN.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_with_invalid_value_before_container_list(self):
        def test():
            config_data = {
                # Node "interfoce" does not exist in this schema.
                "interfoce": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_with_invalid_container_list(self):
        def test():
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                            "description": [{"desc1": "this is an invalid element."}],
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(
                actual.response[0].op, gnmi_pb2.UpdateResult.Operation.UPDATE
            )
            self.assertEqual(
                actual.response[0].message.code,
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            )

        await self.run_gnmi_server_test(test)

    async def test_update_with_invalid_values(self):
        def test():
            config_data1 = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    },
                ]
            }
            config_data2 = {
                # Node "interfoce" does not exist in this schema.
                "interfoce": [
                    {
                        "name": "Ethernet2",
                        "config": {
                            "name": "Ethernet2",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    },
                ]
            }
            config_data3 = {
                "interface": [
                    {
                        # lack of key. "name" is demanded.
                        "config": {
                            "name": "Ethernet3",
                            "type": "iana-if-type:ethernetCsmacd",
                        },
                    },
                ]
            }
            config_data4 = {
                "interface": [
                    {
                        "name": "Ethernet4",
                        "config": {
                            "name": "Ethernet4",
                            "type": "iana-if-type:ethernetCsmacd",
                            # Node "enable" does not exist in this schema.
                            "enable": True,
                        },
                    },
                ]
            }
            config_data5 = {
                "interface": [
                    {
                        "name": "Ethernet5",
                        "config": {
                            "name": "Ethernet5",
                            "type": "iana-if-type:ethernetCsmacd",
                            # Node "description" should not be container-list.
                            "description": [{"blah": True}],
                        },
                    },
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")

            # update1 is set a valid value.
            val1 = gnmi_pb2.TypedValue()
            val1.json_val = json.dumps(config_data1).encode()
            update1 = gnmi_pb2.Update(path=path, val=val1)

            # update2 is set an invalid value.
            val2 = gnmi_pb2.TypedValue()
            val2.json_val = json.dumps(config_data2).encode()
            update2 = gnmi_pb2.Update(path=path, val=val2)

            # update3 is set an invalid value.
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps(config_data3).encode()
            update3 = gnmi_pb2.Update(path=path, val=val3)

            # update4 is set an invalid value.
            val4 = gnmi_pb2.TypedValue()
            val4.json_val = json.dumps(config_data4).encode()
            update4 = gnmi_pb2.Update(path=path, val=val4)

            # update5 is set an invalid value.
            val5 = gnmi_pb2.TypedValue()
            val5.json_val = json.dumps(config_data5).encode()
            update5 = gnmi_pb2.Update(path=path, val=val5)

            request = gnmi_pb2.SetRequest(
                update=[update1, update2, update3, update4, update5]
            )
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])

            expected_path = path
            expected_op = [
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
            ]
            expected_code = [
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
                # update4 has an invalid value but cannot be detected the error in parsing.
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            ]
            for ar, eo, ec in zip(actual.response, expected_op, expected_code):
                self.assertEqual(ar.path, expected_path)
                self.assertEqual(ar.op, eo)
                self.assertEqual(ar.message.code, ec)

        await self.run_gnmi_server_test(test)

    async def test_transaction_with_an_update_failure(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                            "mtu": 1500,
                            "loopback-mode": False,
                        },
                    }
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Check base configuration.
            config_path = gnmi_pb2.Path()
            append_path_element(config_path, "openconfig-interfaces:interfaces")
            append_path_element(config_path, "interface", "name", "Ethernet1")
            append_path_element(config_path, "config")
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

            # Set with delete and updates include a worng update.
            prefix = config_path
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "mtu")
            delete = [path1]
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "loopback-mode")
            val2 = gnmi_pb2.TypedValue()
            val2.json_val = json.dumps(True).encode()
            update2 = gnmi_pb2.Update(path=path2, val=val2)
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "description")
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps("This is Ethernet1.").encode()
            update3 = gnmi_pb2.Update(path=path3, val=val3)
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "enabled")
            val4 = gnmi_pb2.TypedValue()
            # Wrong value to fail.
            val4.json_val = json.dumps("'enabled' should be set with boolean.").encode()
            update4 = gnmi_pb2.Update(path=path4, val=val4)
            update = [update2, update3, update4]
            request = gnmi_pb2.SetRequest(prefix=prefix, delete=delete, update=update)
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(actual.prefix, prefix)
            self.assertEqual(len(actual.response), len(delete) + len(update))
            expected_path = [path1, path2, path3, path4]
            expected_op = [
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
            ]
            expected_code = [
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
            ]
            for ar, ep, eo, ec in zip(
                actual.response, expected_path, expected_op, expected_code
            ):
                self.assertEqual(ar.path, ep)
                self.assertEqual(ar.op, eo)
                self.assertEqual(ar.message.code, ec)

            # Check none of the operations in the request have been applied.
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_transaction_with_a_delete_failure(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                            "mtu": 1500,
                            "loopback-mode": False,
                        },
                    }
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Check base configuration.
            config_path = gnmi_pb2.Path()
            append_path_element(config_path, "openconfig-interfaces:interfaces")
            append_path_element(config_path, "interface", "name", "Ethernet1")
            append_path_element(config_path, "config")
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

            # Set with updates and deletes include a wrong delete.
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-interfaces:interfaces")
            append_path_element(prefix, "interface", "name", "Ethernet1")
            append_path_element(prefix, "config")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "loopback-mode")
            # Wrong path to fail.
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "blah")
            delete = [path1, path2]
            path3 = gnmi_pb2.Path()
            append_path_element(path3, "description")
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps("This is Ethernet1.").encode()
            update3 = gnmi_pb2.Update(path=path3, val=val3)
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "enabled")
            val4 = gnmi_pb2.TypedValue()
            val4.json_val = json.dumps(False).encode()
            update4 = gnmi_pb2.Update(path=path4, val=val4)
            update = [update3, update4]
            request = gnmi_pb2.SetRequest(prefix=prefix, delete=delete, update=update)
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(actual.prefix, prefix)
            expected_path = [path1, path2, path3, path4]
            expected_op = [
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
            ]
            expected_code = [
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.INVALID_ARGUMENT.value[0],
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.ABORTED.value[0],
            ]
            self.assertEqual(len(actual.response), len(delete) + len(update))
            for ar, ep, eo, ec in zip(
                actual.response, expected_path, expected_op, expected_code
            ):
                self.assertEqual(ar.path, ep)
                self.assertEqual(ar.op, eo)
                self.assertEqual(ar.message.code, ec)

            # Check none of the operations in the request have been applied.
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)

    async def test_transaction_with_apply_failure(self):
        def test():
            # Prepare base configuration.
            config_data = {
                "interface": [
                    {
                        "name": "Ethernet1",
                        "config": {
                            "name": "Ethernet1",
                            "type": "iana-if-type:ethernetCsmacd",
                            "enabled": True,
                            "mtu": 1500,
                            "loopback-mode": False,
                        },
                    }
                ]
            }
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            val = gnmi_pb2.TypedValue()
            val.json_val = json.dumps(config_data).encode()
            update = gnmi_pb2.Update(path=path, val=val)
            request = gnmi_pb2.SetRequest(update=[update])
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.OK)

            # Check base configuration.
            config_path = gnmi_pb2.Path()
            append_path_element(config_path, "openconfig-interfaces:interfaces")
            append_path_element(config_path, "interface", "name", "Ethernet1")
            append_path_element(config_path, "config")
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

            # Failed to apply due to update a read only leaf node.
            prefix = gnmi_pb2.Path()
            append_path_element(prefix, "openconfig-interfaces:interfaces")
            append_path_element(prefix, "interface", "name", "Ethernet1")
            path1 = gnmi_pb2.Path()
            append_path_element(path1, "config")
            append_path_element(path1, "mtu")
            delete = [path1]
            path2 = gnmi_pb2.Path()
            append_path_element(path2, "config")
            append_path_element(path2, "loopback-mode")
            val2 = gnmi_pb2.TypedValue()
            val2.json_val = json.dumps(True).encode()
            update2 = gnmi_pb2.Update(path=path2, val=val2)
            path3 = gnmi_pb2.Path()
            # Read only leaf node to fail.
            append_path_element(path3, "state")
            append_path_element(path3, "description")
            val3 = gnmi_pb2.TypedValue()
            val3.json_val = json.dumps("This is Ethernet1.").encode()
            update3 = gnmi_pb2.Update(path=path3, val=val3)
            path4 = gnmi_pb2.Path()
            append_path_element(path4, "config")
            append_path_element(path4, "enabled")
            val4 = gnmi_pb2.TypedValue()
            val4.json_val = json.dumps(False).encode()
            update4 = gnmi_pb2.Update(path=path4, val=val4)
            update = [update2, update3, update4]
            request = gnmi_pb2.SetRequest(prefix=prefix, delete=delete, update=update)
            actual, code = self.gnmi_set(request)
            self.assertEqual(code, grpc.StatusCode.ABORTED)
            self.assertEqual(actual.message.code, grpc.StatusCode.ABORTED.value[0])
            self.assertEqual(actual.prefix, prefix)

            expected_path = [path1, path2, path3, path4]
            expected_op = [
                gnmi_pb2.UpdateResult.Operation.DELETE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
                gnmi_pb2.UpdateResult.Operation.UPDATE,
            ]
            expected_code = [
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.ABORTED.value[0],
                # TODO: In this case, this code should be set to
                #   INVALID_ARGUMENT. But the error cannot be detected
                #   properly.
                # grpc.StatusCode.INVALID_ARGUMENT.value[0],
                grpc.StatusCode.ABORTED.value[0],
                grpc.StatusCode.ABORTED.value[0],
            ]
            self.assertEqual(len(actual.response), len(delete) + len(update))
            for ar, ep, eo, ec in zip(
                actual.response, expected_path, expected_op, expected_code
            ):
                self.assertEqual(ar.path, ep)
                self.assertEqual(ar.op, eo)
                self.assertEqual(ar.message.code, ec)

            # Check none of the operations in the request have been applied.
            request = gnmi_pb2.GetRequest(path=[config_path])
            actual, code = self.gnmi_get(request)
            self.assertEqual(code, grpc.StatusCode.OK)
            act = json.loads(
                actual.notification[0].update[0].val.json_val.decode("utf-8")
            )
            expected = {
                "name": "Ethernet1",
                "type": "iana-if-type:ethernetCsmacd",
                "enabled": True,
                "mtu": 1500,
                "loopback-mode": False,
            }
            self.assertEqual(act, expected)

        await self.run_gnmi_server_test(test)


class TestSubscribe(gNMIServerTestCase):
    """Tests gNMI server Subscribe Service."""

    MOCK_MODULES = ["goldstone-telemetry"]
    NOTIF_SERVER = "goldstone-telemetry"
    NOTIF_PATH = "goldstone-telemetry:telemetry-notify-event"
    WAIT_CREATION = 0.1
    WAIT_NOTIFICATION = 0.1

    async def test_subscribe_stream_target_defined(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(
                path=path, mode=gnmi_pb2.SubscriptionMode.TARGET_DEFINED
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "TARGET_DEFINED",
                                        "suppress-redundant": False,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "false",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = False
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_on_change(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(
                path=path, mode=gnmi_pb2.SubscriptionMode.ON_CHANGE
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "ON_CHANGE",
                                        "suppress-redundant": False,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "false",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = False
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_on_change_heartbeat(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            hb_interval = 10 * 1000 * 1000 * 1000
            s1 = gnmi_pb2.Subscription(
                path=path,
                mode=gnmi_pb2.SubscriptionMode.ON_CHANGE,
                heartbeat_interval=hb_interval,
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "ON_CHANGE",
                                        "suppress-redundant": False,
                                        "heartbeat-interval": hb_interval,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked heartbeat expired update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_sample(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s_interval = 5 * 1000 * 1000 * 1000
            s1 = gnmi_pb2.Subscription(
                path=path,
                mode=gnmi_pb2.SubscriptionMode.SAMPLE,
                sample_interval=s_interval,
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "SAMPLE",
                                        "sample-interval": s_interval,
                                        "suppress-redundant": False,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked sampling update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_sample_suppress_redundant(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s_interval = 5 * 1000 * 1000 * 1000
            s1 = gnmi_pb2.Subscription(
                path=path,
                mode=gnmi_pb2.SubscriptionMode.SAMPLE,
                sample_interval=s_interval,
                suppress_redundant=True,
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "SAMPLE",
                                        "sample-interval": s_interval,
                                        "suppress-redundant": True,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # No sampling update events and streaming updates because of suppress-redundant.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_sample_suppress_redundant_heartbeat(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s_interval = 5 * 1000 * 1000 * 1000
            hb_interval = 10 * 1000 * 1000 * 1000
            s1 = gnmi_pb2.Subscription(
                path=path,
                mode=gnmi_pb2.SubscriptionMode.SAMPLE,
                sample_interval=s_interval,
                suppress_redundant=True,
                heartbeat_interval=hb_interval,
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "SAMPLE",
                                        "sample-interval": s_interval,
                                        "suppress-redundant": True,
                                        "heartbeat-interval": hb_interval,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked heartbeat expired update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_stream_updates_only(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(
                path=path, mode=gnmi_pb2.SubscriptionMode.TARGET_DEFINED
            )
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    updates_only=True,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "STREAM",
                            "updates-only": True,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                        "mode": "TARGET_DEFINED",
                                        "suppress-redundant": False,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # No initial updates.

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "false",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive streaming updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = False
            self.assertEqual(act, expected)

            # No sync-responses.

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_once(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "ONCE",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

            # Was the subscribe-request deleted?
            self.assertEqual(len(self.servicer._subscribe_requests), 0)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    with self.assertRaises(sysrepo.SysrepoNotFoundError):
                        sess.get_data(
                            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
                        )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_once_updates_only(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    updates_only=True,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "ONCE",
                            "updates-only": True,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            notifs = [
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # No initial updates.

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

            # Was the subscribe-request deleted?
            self.assertEqual(len(self.servicer._subscribe_requests), 0)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    with self.assertRaises(sysrepo.SysrepoNotFoundError):
                        sess.get_data(
                            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
                        )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_poll(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.POLL,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "POLL",
                            "updates-only": False,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send a poll request.
            expected_time_min = time.time_ns()
            poll_request = gnmi_pb2.SubscribeRequest(poll=gnmi_pb2.Poll())
            self.rpc.send_request(poll_request)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive polling updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the polling updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

            # Was the subscribe-request deleted?
            self.assertEqual(len(self.servicer._subscribe_requests), 0)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    with self.assertRaises(sysrepo.SysrepoNotFoundError):
                        sess.get_data(
                            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
                        )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_poll_updates_only(self):
        def test():
            # Create a Subscribe RPC session.
            path_str = "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled"
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.POLL,
                    updates_only=True,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Verify configuraion.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]
                    expected = {
                        "id": generated_id,
                        "config": {
                            "id": generated_id,
                            "mode": "POLL",
                            "updates-only": True,
                        },
                        "subscriptions": {
                            "subscription": [
                                {
                                    "id": 0,
                                    "config": {
                                        "id": 0,
                                        "path": path_str,
                                    },
                                }
                            ]
                        },
                    }
                    self.assertEqual(sr, expected)

            # Send mocked events.
            notifs = [
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # No initial updates.

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send a poll request.
            poll_request = gnmi_pb2.SubscribeRequest(poll=gnmi_pb2.Poll())
            self.rpc.send_request(poll_request)

            time.sleep(self.WAIT_NOTIFICATION)

            # No polling updates.

            # Receive the sync-response of the polling updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

            # Was the subscribe-request deleted?
            self.assertEqual(len(self.servicer._subscribe_requests), 0)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    with self.assertRaises(sysrepo.SysrepoNotFoundError):
                        sess.get_data(
                            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
                        )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_a_leaf(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

        await self.run_gnmi_server_test(test)

    async def test_subscribe_a_leaf_list(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-terminal-device:terminal-device")
            append_path_element(path, "logical-channels")
            append_path_element(path, "channel", "index", "1")
            append_path_element(path, "ingress")
            append_path_element(path, "state")
            append_path_element(path, "physical-channel")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": (
                        "/openconfig-terminal-device:terminal-device/logical-channels/channel[index='1']"
                        "/ingress/state/physical-channel"
                    ),
                    "json-data": "[1, 2, 3]",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = [1, 2, 3]
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

        await self.run_gnmi_server_test(test)

    async def test_subscribe_a_container(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/name",
                    "json-data": '"Interface1/0/1"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/type",
                    "json-data": '"iana-if-type:ethernetCsmacd"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/mtu",
                    "json-data": "1500",
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            ## Verify name.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "name")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "Interface1/0/1"
            self.assertEqual(act, expected)
            ## Verify type.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "type")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "iana-if-type:ethernetCsmacd"
            self.assertEqual(act, expected)
            ## Verify mtu.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "mtu")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = 1500
            self.assertEqual(act, expected)
            ## Verify enabled.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

        await self.run_gnmi_server_test(test)

    async def test_subscribe_a_container_list(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface")
            s1 = gnmi_pb2.Subscription(path=path)
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.ONCE,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/name",
                    "json-data": '"Interface1/0/1"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/name",
                    "json-data": '"Interface1/0/1"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/2']/name",
                    "json-data": '"Interface1/0/2"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/2']/state/name",
                    "json-data": '"Interface1/0/2"',
                },
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/2']/state/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            ## Verify Interface1/0/1 name.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "name")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "Interface1/0/1"
            self.assertEqual(act, expected)
            ## Verify Interface1/0/1 state/name.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "name")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "Interface1/0/1"
            self.assertEqual(act, expected)
            ## Verify Interface1/0/1 state/enabled.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)
            ## Verify Interface1/0/2 name.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/2")
            append_path_element(path, "name")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "Interface1/0/2"
            self.assertEqual(act, expected)
            ## Verify Interface1/0/2 state/name.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/2")
            append_path_element(path, "state")
            append_path_element(path, "name")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = "Interface1/0/2"
            self.assertEqual(act, expected)
            ## Verify Interface1/0/2 state/enabled.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/2")
            append_path_element(path, "state")
            append_path_element(path, "enabled")
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Close the RPC session.
            self.rpc.requests_closed()
            _, code, _ = self.rpc.termination()
            self.assertEqual(code, grpc.StatusCode.OK)

        await self.run_gnmi_server_test(test)

    async def test_subscribe_trigger_created(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "config")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path, mode="ON_CHANGE")
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # No initial updates.

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked create events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/config/enabled",
                    "json-data": "true",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_trigger_updated(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "config")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path, mode="ON_CHANGE")
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/config/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked update events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/config/enabled",
                    "json-data": "false",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = False
            self.assertEqual(act, expected)

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)

    async def test_subscribe_trigger_deleted(self):
        def test():
            # Create a Subscribe RPC session.
            path = gnmi_pb2.Path()
            append_path_element(path, "openconfig-interfaces:interfaces")
            append_path_element(path, "interface", "name", "Interface1/0/1")
            append_path_element(path, "config")
            append_path_element(path, "enabled")
            s1 = gnmi_pb2.Subscription(path=path, mode="ON_CHANGE")
            subscriptions = [s1]
            request = gnmi_pb2.SubscribeRequest(
                subscribe=gnmi_pb2.SubscriptionList(
                    mode=gnmi_pb2.SubscriptionList.Mode.STREAM,
                    subscription=subscriptions,
                ),
            )
            self.rpc = self.gnmi_subscribe(request)

            time.sleep(self.WAIT_CREATION)

            # Get generated request-id.
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("running")
                    subscribe_requests = sess.get_data(
                        "/goldstone-telemetry:subscribe-requests/subscribe-request"
                    )
                    srs = list(
                        subscribe_requests["subscribe-requests"]["subscribe-request"]
                    )
                    self.assertEqual(len(srs), 1)
                    sr = srs[0]
                    generated_id = sr["id"]

            # Send mocked events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "UPDATE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/config/enabled",
                    "json-data": "true",
                },
                {
                    "type": "SYNC_RESPONSE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive initial updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.update[0].path, path)
            act = json.loads(actual.update.update[0].val.json_val.decode("utf-8"))
            expected = True
            self.assertEqual(act, expected)

            # Receive the sync-response of the initial updates.
            actual = self.rpc.take_response()
            self.assertEqual(actual.sync_response, True)

            # Send mocked delete events.
            expected_time_min = time.time_ns()
            notifs = [
                {
                    "type": "DELETE",
                    "request-id": generated_id,
                    "subscription-id": 0,
                    "path": "/openconfig-interfaces:interfaces/interface[name='Interface1/0/1']/config/enabled",
                },
            ]
            self.set_mock_notifs_data(self.NOTIF_SERVER, self.NOTIF_PATH, notifs)
            self.send_mock_notifs(self.NOTIF_SERVER)

            time.sleep(self.WAIT_NOTIFICATION)

            # Receive updates.
            actual = self.rpc.take_response()
            expected_time_max = time.time_ns()
            self.assertGreater(actual.update.timestamp, expected_time_min)
            self.assertLess(actual.update.timestamp, expected_time_max)
            self.assertEqual(actual.update.delete[0], path)

            # Close the RPC session.
            self.rpc.requests_closed()
            # NOTE: rpc.termination does not work for tests. We cannot close the RPC and confirm teardown procedure.
            # _, code, _ = self.rpc.termination()
            # self.assertEqual(code, grpc.StatusCode.OK)
            #
            # Was the subscribe-request deleted?
            # self.assertEqual(len(self.servicer._subscribe_requests), 0)
            # with sysrepo.SysrepoConnection() as conn:
            #     with conn.start_session() as sess:
            #         sess.switch_datastore("running")
            #         with self.assertRaises(sysrepo.SysrepoNotFoundError):
            #             sess.get_data(
            #                 f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{generated_id}']"
            #             )

        await self.run_gnmi_server_test(test)


if __name__ == "__main__":
    unittest.main()
