import unittest
import sysrepo

class TestSysrepo(unittest.TestCase):
    def test_module_install(self):
        conn = sysrepo.SysrepoConnection()
        for module in ["interfaces", "vlan", "transponder", "platform", "uplink-failure-detection"]:
            conn.install_module(f"yang/goldstone-{module}.yang", "yang")
