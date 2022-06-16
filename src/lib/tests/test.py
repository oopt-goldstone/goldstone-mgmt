import unittest
from unittest import mock

import logging
from goldstone.lib.connector.sysrepo import Connector as SRConnector, wrap_sysrepo_error

from goldstone.lib.errors import *
import sysrepo


console = logging.StreamHandler()
logger = logging.getLogger("goldstone")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)


class TestSysrepoConnector(unittest.TestCase):
    def test_wrap_sysrepo_error(self):
        def f(*args, **kwargs):
            raise sysrepo.SysrepoInvalArgError("test")

        with self.assertRaisesRegex(InvalArgError, "test"):
            wrap_sysrepo_error(f)(mock.MagicMock())

        def f(*args, **kwargs):
            raise sysrepo.SysrepoValidationFailedError("validation fail")

        with self.assertRaisesRegex(ValidationFailedError, "validation fail"):
            wrap_sysrepo_error(f)(mock.MagicMock())

    def test_leaf_list_edit(self):
        conn = SRConnector()
        conn.delete_all("goldstone-interfaces")
        conn.apply()
        sess = conn.running_session
        ifname = "eth0"
        prefix = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
        conn.set(prefix + "/config/name", ifname)
        xpath = prefix + "/ethernet/auto-negotiate/config/advertised-speeds"
        conn.set(xpath, ["SPEED_10G"])
        conn.set(prefix + "/config/admin-status", "UP")
        conn.apply()

        conf = conn.get(prefix + "/config/admin-status")
        self.assertEqual(conf, "UP")
        conf = conn.get(xpath)
        self.assertEqual(conf, ["SPEED_10G"])

        def test(speeds):
            conn.set(xpath, speeds)
            conn.apply()

            conf = conn.get(prefix + "/config/admin-status")
            self.assertEqual(conf, "UP")
            conf = conn.get(xpath, [])
            self.assertEqual(conf, speeds)

        test(["SPEED_40G"])
        test(["SPEED_10G", "SPEED_40G"])
        test([])
        test(["SPEED_40G"])
        test(["SPEED_10G"])
        test(["SPEED_40G", "SPEED_100G"])


class TestCLI(unittest.TestCase):
    def test_sysrepo_connector_notification(self):
        conn = SRConnector()
        session = conn.new_session()
        session.subscribe_notifications(lambda v: v)
        session.stop()


if __name__ == "__main__":
    unittest.main()
