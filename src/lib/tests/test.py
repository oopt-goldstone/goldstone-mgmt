import unittest
import logging
from goldstone.lib.connector.netconf import Connector as NCConnector
from goldstone.lib.connector.sysrepo import Connector as SRConnector

console = logging.StreamHandler()
logger = logging.getLogger("goldstone")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)


class TestCLI(unittest.TestCase):

    # demonstrate how to use NETCONF Connector
    @unittest.skip("skip netconf test")
    def test_netconf_connector(self):
        args = {
            "host": "127.0.0.1",
            "hostkey_verify": "false",
            "username": "admin",
            "password": "admin",
        }

        conn = NCConnector(**args)
        v = conn.get_operational("/goldstone-interfaces:interfaces/interface/name")
        self.assertTrue(len(v) > 0)
        v = conn.get_operational(
            "/goldstone-interfaces:interfaces/interface[name='Ethernet1_1']", one=True
        )
        self.assertTrue(v != None)

    def test_sysrepo_connector_notification(self):
        conn = SRConnector()
        session = conn.new_session()
        session.subscribe_notifications(lambda v: v)
        session.stop()


if __name__ == "__main__":
    unittest.main()
