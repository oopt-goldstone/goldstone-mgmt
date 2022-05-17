"""Tests for path utilities."""


import unittest
from goldstone.lib.connector.sysrepo import Connector
from goldstone.system.telemetry.path import PathParser


class TestPathParser(unittest.TestCase):
    """Tests for PathParser."""

    def setUp(self):
        self.conn = Connector()
        self.ctx = self.conn.ctx

    def tearDown(self) -> None:
        self.conn.stop()

    def test_valid_path(self):
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/name"
        p = PathParser(self.ctx)
        self.assertTrue(p.is_valid_path(path))

    def test_invalid_path(self):
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/unknown-node"
        p = PathParser(self.ctx)
        self.assertFalse(p.is_valid_path(path))

    def test_parse_dict(self):
        data = {
            "interfaces": {
                "interface": [
                    {
                        "name": "Interface1/0/1",
                        "config": {
                            "name": "Interface1/0/1",
                            "admin-status": "UP",
                        },
                        "state": {
                            "name": "Interface1/0/1",
                            "admin-status": "DOWN",
                        },
                    }
                ]
            }
        }
        path = (
            "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config"
        )
        p = PathParser(self.ctx)
        parsed_data = p.parse_dict_into_leaves(data, path)
        expected = {path + "/name": "Interface1/0/1", path + "/admin-status": "UP"}
        self.assertEqual(parsed_data, expected)


if __name__ == "__main__":
    unittest.main()
