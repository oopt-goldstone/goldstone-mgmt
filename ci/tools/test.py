#!/usr/bin/env python3

import paramiko
import time
import sys
import unittest
import os

from .common import *

HOST = os.getenv("GS_TEST_HOST")
assert HOST

USERNAME = os.getenv("GS_TEST_USERNAME", "root")
PASSWORD = os.getenv("GS_TEST_PASSWORD", "x1")


class TestBase(unittest.TestCase):
    def setUp(self):
        self.cli = paramiko.SSHClient()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.cli.connect(HOST, username=USERNAME, password=PASSWORD)

    def tearDown(self):
        self.cli.close()

    def ssh(self, command):
        return ssh(self.cli, command)

    def gscli(self, command):
        return self.ssh(f'gscli -c "{command}"')


class TestSouthONLP(TestBase):
    def test_platform(self):
        # ADD test for platform CLIs here
        output = self.ssh('gscli -c "show datastore /goldstone-platform:* operational"')
        self.assertTrue("piu" in output)
        self.assertTrue("transceiver" in output)
        self.gscli("show chassis-hardware fan")
        self.gscli("show chassis-hardware led")
        self.gscli("show chassis-hardware psu")
        self.gscli("show chassis-hardware thermal")
        self.gscli("show chassis-hardware system")
        self.gscli("show chassis-hardware transceiver table")
        self.gscli("show chassis-hardware transceiver")
        self.gscli("show chassis-hardware piu table")
        output = self.gscli("show chassis-hardware piu")
        self.assertTrue("piu" in output)
        self.assertTrue("PRESENT" in output)
        output = self.gscli("show tech-support")
        self.assertTrue("FAN INFORMATION" in output)


class TestSouthSystem(TestBase):
    def test_show_version(self):
        self.gscli("show version")

    def test_mgmt_if_cmds(self):
        with self.assertRaisesRegex(SSHException, "does not satisfy the constraint"):
            self.gscli("mgmt-if eth0; ip address 999.999.999.999/24")
        with self.assertRaisesRegex(
            SSHException,
            "Entered address is not in the expected format - A.B.C.D\/\<mask\>",
        ):
            self.gscli("mgmt-if eth0; ip address 999.999.999.999.24")
        output = self.gscli(
            "mgmt-if eth0; ip address 20.20.20.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip address 20.20.20.0/24" in output)

        with self.assertRaisesRegex(SSHException, "does not satisfy the constraint"):
            self.gscli(
                "mgmt-if eth0; no ip address 999.999.999.999/24",
            )

        with self.assertRaisesRegex(
            SSHException,
            "Entered address is not in the expected format - A.B.C.D\/\<mask\>",
        ):
            self.gscli("mgmt-if eth0; ip address 999.999.999.999.24")

        output = self.gscli(
            "mgmt-if eth0; no ip address 20.20.20.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip address 20.20.20.0/24" not in output)

        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.gscli("mgmt-if eth0; ip route 10.10.10.117")

        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.gscli("mgmt-if eth0; ip route 10.10.10.117/35")

        output = self.gscli(
            "mgmt-if eth0; ip route 30.30.30.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip route 30.30.30.0/24" in output)

        output = self.gscli("show ip route")
        self.assertTrue("30.30.30.0/24" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip route 30.30.30.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip route 30.30.30.0/24" not in output)

        output = self.gscli("show ip route")
        self.assertTrue("30.30.30.0/24" not in output)

        output = self.gscli(
            "mgmt-if eth0; ip route 30.20.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 30.20.0.0/16" in output)
        output = self.gscli(
            "mgmt-if eth0; ip route 20.10.20.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip route 20.10.20.0/24" in output)
        output = self.gscli(
            "mgmt-if eth0; ip route 30.20.20.0/24; show running-config mgmt-if",
        )
        self.assertTrue("ip route 30.20.20.0/24" in output)
        output = self.gscli("show ip route")
        self.assertTrue("30.20.0.0/16" in output)
        self.assertTrue("20.10.20.0/24" in output)
        self.assertTrue("30.20.20.0/24" in output)

        self.gscli("clear ip route")

        output = self.gscli("show ip route")
        self.assertTrue("30.20.0.0/16" not in output)
        self.assertTrue("20.10.20.0/24" not in output)
        self.assertTrue("30.20.20.0/24" not in output)

    def test_mgmt_intf(self):
        self.gscli("show arp")
        self.gscli("ping 10.10.10.250 -c 4")
        output = self.gscli("show arp")
        self.assertTrue("10.10.10.250" in output)
        self.gscli("clear arp")
        output = self.gscli("show arp")
        self.assertTrue("10.10.10.250" not in output)
        self.gscli("show arp")
        self.gscli("ping 10.10.10.100 -c 4")
        output = self.gscli("show arp")
        self.assertTrue("10.10.10.100" in output)
        self.gscli("clear arp")
        self.gscli("clear arp")
        output = self.gscli("show arp")
        self.assertTrue("10.10.10.100" not in output)

    def test_system_reconcile(self):
        output = self.gscli(
            "mgmt-if eth0; ip route 31.21.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 31.21.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; ip address 20.21.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 20.21.0.0/16" in output)

        output = self.gscli("show ip route")
        self.assertTrue("31.21.0.0/16" in output)

        self.ssh("systemctl restart gs-south-system")
        time.sleep(10)

        output = self.gscli("show ip route")
        self.assertTrue("31.21.0.0/16" in output)
        output = self.gscli("show running-config mgmt-if")
        self.assertTrue("ip address 20.21.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip route 31.21.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 31.21.0.0/16" not in output)

        output = self.gscli(
            "mgmt-if eth0; no ip address 20.21.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 20.21.0.0/16" not in output)

        # case for saving a tree without leaf address
        output = self.gscli(
            "mgmt-if eth0; ip address 56.10.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 56.10.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip address 56.10.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 56.10.0.0/16" not in output)

        output = self.gscli(
            "mgmt-if eth0; ip route 100.17.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 100.17.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip route 100.17.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 100.17.0.0/16" not in output)

        self.ssh("systemctl restart gs-south-system")
        time.sleep(10)

        output = self.gscli(
            "mgmt-if eth0; ip address 56.10.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 56.10.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip address 56.10.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip address 56.10.0.0/16" not in output)

        output = self.gscli(
            "mgmt-if eth0; ip route 100.17.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 100.17.0.0/16" in output)

        output = self.gscli(
            "mgmt-if eth0; no ip route 100.17.0.0/16; show running-config mgmt-if",
        )
        self.assertTrue("ip route 100.17.0.0/16" not in output)


class TestSouthGearbox(TestBase):
    def test_interface(self):
        output = self.gscli("show interface brief")
        self.assertTrue("Ethernet1/1/1" in output)

        output = self.gscli("interface Ethernet1/1/1; show")
        self.assertTrue("admin-status" in output)
        self.assertTrue("oper-status" in output)
        self.assertTrue("fec" in output)
        self.assertTrue("speed" in output)

        self.gscli("interface Ethernet1/1/1; admin-status up")
        output = self.gscli("interface Ethernet1/1/1; show")
        for line in output.split("\n"):
            if "admin-status" in line:
                self.assertTrue("up" in line)
                break

        self.gscli("interface Ethernet1/1/1; admin-status down")
        output = self.gscli("interface Ethernet1/1/1; show")
        for line in output.split("\n"):
            if "admin-status" in line:
                self.assertTrue("down" in line)
                break

        self.gscli("interface Ethernet1/1/1; no admin-status")
        output = self.gscli("interface Ethernet1/1/1; show")
        for line in output.split("\n"):
            if "admin-status" in line:
                self.assertTrue("down" in line)
                break

    def test_mtu(self):
        ifname = "Ethernet1/1/1"
        self.gscli(f"interface {ifname}; no mtu")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("10000" in output)
        self.gscli(f"interface {ifname}; mtu 9000")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("9000" in output)

        with self.assertRaises(SSHException):
            self.gscli(f"interface {ifname}; mtu 20000")

        self.gscli(f"interface {ifname}; no mtu")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("10000" in output)

    def test_fec(self):
        ifname = "Ethernet1/1/1"
        self.gscli(f"interface {ifname}; no fec")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("rs" in output)
        with self.assertRaises(SSHException):
            self.gscli(f"interface {ifname}; fec none")

        with self.assertRaises(SSHException):
            self.gscli(f"interface {ifname}; fec fc")

        self.gscli(f"interface {ifname}; fec rs")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("rs" in output)

        self.gscli(f"interface {ifname}; no fec")
        output = self.gscli(f"interface {ifname}; show")
        self.assertTrue("rs" in output)

    def test_show_counter(self):
        self.gscli(f"show interface counter Ethernet1/1/1")
        self.gscli(f"show interface counter")
        self.gscli(f"show interface counter table")

    def test_gearbox(self):
        self.gscli("show gearbox")
        self.gscli("gearbox 1; admin-status up")
        self.gscli("gearbox 1; admin-status down")
        self.gscli("gearbox 1; no admin-status")
        self.gscli("gearbox 1; show")

        for _ in range(120):
            output = self.gscli("gearbox 1; show")
            for line in output.split("\n"):
                if "oper-status" in line and "up" in line:
                    return
            time.sleep(1)
        else:
            raise Exception("gearbox didn't come up")


class TestSouthSONiC(TestBase):
    def test_vlan(self):
        self.gscli("show vlan details")
        self.gscli("vlan 1000")
        self.gscli("show vlan details")
        self.gscli("vlan 2000")
        self.gscli("show vlan details")
        self.gscli("vlan range 1000-1010")
        self.gscli("show vlan details")
        self.gscli("vlan range 200-205,250,295-300")
        self.gscli("show vlan details")
        self.gscli("no vlan range 200-205,250")
        self.gscli("show vlan details")
        self.gscli("no vlan 2000")
        self.gscli("show vlan details")
        self.gscli("no vlan 1000")
        self.gscli("show vlan details")
        self.gscli("show interface brief")
        self.gscli("show interface description")
        self.gscli("show tech-support")
        self.gscli("show running-config")
        self.gscli("show running-config interface")
        self.gscli("show running-config vlan")

    #        with self.assertRaisesRegex(SSHException, "The vlan-range entered is invalid"):
    #            self.ssh('gscli -c "vlan range 25-19"')

    def test_auto_nego(self):
        self.gscli("interface Ethernet3_1; auto-negotiate enable")
        self.gscli("interface Ethernet3_1; auto-negotiate disable")

        self.gscli("interface Ethernet3_1; auto-negotiate enable")
        self.ssh("kubectl rollout restart ds/south-sonic")
        check_pod(self.cli, "south-sonic")
        output = self.gscli("show running-config interface")
        self.assertTrue("auto-negotiate enable" in output)
        self.gscli("interface Ethernet3_1; no auto-negotiate")
        output = self.gscli("show running-config interface")
        self.assertTrue("auto-negotiate" not in output)
        self.gscli("interface Ethernet3_1; auto-negotiate enable")

        with self.assertRaisesRegex(
            SSHException, "../../auto-negotiate/config/enabled = 'false'"
        ):
            self.gscli("interface Ethernet3_1; interface-type SR4")

        with self.assertRaisesRegex(
            SSHException, "../../auto-negotiate/config/enabled = 'false'"
        ):
            self.gscli("interface Ethernet3_1; fec rs")

        with self.assertRaisesRegex(
            SSHException, "../../auto-negotiate/config/enabled = 'false'"
        ):
            self.gscli("interface Ethernet3_1; speed 40G")

        self.gscli("interface Ethernet3_1; auto-negotiate advertise 40G")
        output = self.ssh('gscli -c "interface Ethernet3_1; show" | grep advertise')

    def test_auto_nego_with_interface_type(self):
        self.gscli("interface Ethernet3_1; no auto-negotiate")
        self.gscli("interface Ethernet3_1; interface-type CR4")
        self.gscli("interface Ethernet3_1; auto-negotiate enable")
        self.gscli("interface Ethernet3_1; show")

    def test_intf_type(self):
        self.gscli("interface Ethernet1_1; interface-type SR4")
        self.gscli("interface Ethernet1_1; interface-type KR4")

        self.gscli("interface Ethernet1_1; interface-type CR4")
        self.ssh("kubectl rollout restart ds/south-sonic")
        check_pod(self.cli, "south-sonic")
        output = self.gscli("show running-config interface")
        self.assertTrue("interface-type CR4" in output)
        self.gscli("interface Ethernet1_1; no interface-type")
        output = self.gscli("show running-config interface")
        self.assertTrue("interface-type" not in output)

    def test_speed_intftype(self):
        with self.assertRaisesRegex(SSHException, "invalid"):
            self.gscli("interface Ethernet4_1; speed 10000")
        with self.assertRaisesRegex(SSHException, "Unsupported interface type"):
            self.gscli("interface Ethernet4_1; interface-type SR")

    def test_ufd(self):
        self.gscli("ufd ufd1")
        self.gscli("interface Ethernet1_1; ufd ufd1 uplink")
        self.gscli("interface Ethernet2_1; ufd ufd1 downlink")
        self.gscli("interface Ethernet4_1; ufd ufd1 downlink")
        output = self.gscli("ufd ufd1; show")
        self.assertTrue("Ethernet1_1" in output)
        self.assertTrue("Ethernet2_1" in output)
        self.assertTrue("Ethernet4_1" in output)

        with self.assertRaises(SSHException):
            self.gscli("interface Ethernet5_1; ufd ufd1 uplink")

        with self.assertRaises(SSHException):
            self.gscli("interface Ethernet1_1; ufd ufd1 downlink")

        self.gscli("ufd 10")
        self.gscli("interface Ethernet6_1; ufd 10 uplink")
        self.gscli("interface Ethernet7_1; ufd 10 downlink")
        self.gscli("interface Ethernet6_1; shutdown")
        output = self.gscli("show interface brief")
        self.assertTrue("Ethernet7_1  |   dormant  " in output)
        output = self.gscli("show running-config interface")
        self.assertTrue("ufd 10 downlink" in output)

    def test_portchannel(self):
        self.gscli("portchannel PortChannel10")
        self.gscli("interface Ethernet1_1; portchannel PortChannel10")
        self.gscli("interface Ethernet2_1; portchannel PortChannel10")
        self.gscli("interface Ethernet4_1; portchannel PortChannel10")
        output = self.gscli("portchannel PortChannel10; show")
        self.assertTrue("Ethernet1_1" in output)
        self.assertTrue("Ethernet2_1" in output)
        self.assertTrue("Ethernet4_1" in output)
        output = self.gscli("show running-config interface")
        self.assertTrue("portchannel PortChannel10" in output)
        self.gscli("portchannel PortChannel20")

        with self.assertRaisesRegex(SSHException, "points to a non-existing leaf"):
            self.gscli("interface Ethernet1_1; portchannel PortChannel30")

        self.gscli("portchannel PortChannel9")
        self.gscli("portchannel PortChannel99")
        self.gscli("portchannel PortChannel999")
        self.gscli("portchannel PortChannel9999")
        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.gscli("portchannel PortChannel10000")

        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.gscli("portchannel Lag10")

        self.gscli("interface Ethernet10_1; portchannel PortChannel9")
        output = self.ssh("ip link | grep -w PortChannel9")
        self.assertTrue("PortChannel9" in output)
        output = self.ssh(
            "kubectl exec -t usonic-cli -- show interface status|grep Ethernet10_1"
        )
        self.assertTrue("PortChannel9" in output)
        self.gscli("interface Ethernet10_1; no portchannel PortChannel9")
        output = self.ssh(
            "kubectl exec -t usonic-cli -- show interface status|grep Ethernet10_1"
        )
        self.assertTrue("PortChannel9" not in output)
        self.gscli("portchannel PortChannel9; shutdown")
        self.gscli("portchannel PortChannel9; no shutdown")
        self.gscli("no portchannel PortChannel9")

        with self.assertRaises(SSHException):
            self.ssh("ip link | grep -w PortChannel9")

    def test_vlan_member_add_delete(self):
        self.gscli("show vlan details")
        self.gscli("vlan 1000")
        self.gscli("show vlan details")
        self.gscli(
            "interface Ethernet1_1; no shutdown; switchport mode trunk vlan 1000; show",
        )
        self.gscli("show vlan details")
        self.gscli(
            "interface Ethernet2_1; no shutdown; switchport mode trunk vlan 1000; show",
        )
        self.gscli("show vlan details")
        self.gscli(
            "interface Ethernet1_1; no shutdown; no switchport mode trunk vlan 1000; show",
        )

        with self.assertRaises(
            SSHException,
        ):
            self.gscli("interface Ethernet1_1; switchport mode trunk vlab 1000")

        with self.assertRaises(
            SSHException,
        ):
            self.gscli(
                "interface Ethernet1_1; switchport mode trunk access 1000",
            )

        self.gscli("interface Ethernet1_1; switchport mode trunk vlan 1000")
        output = self.gscli("show vlan details")
        self.assertTrue("Ethernet1_1" in output)

        #    try:
        #        ssh(
        #            cli, 'gscli -c "interface Ethernet1_1; no switchport mode access vlan 1000"'
        #        )
        #    except SSHException as e:
        #        assert "Incorrect mode given" in e.stderr
        #    else:
        #        raise Exception(
        #            "failed to fail with an invalid cmd no switchport mode access vlan 1000"
        #
        with self.assertRaises(
            SSHException,
        ):
            self.gscli(
                "interface Ethernet1_1; no switchport mode trunk access 1000",
            )

        self.gscli("interface Ethernet1_1; no switchport mode trunk vlan 1000")
        output = self.gscli("show vlan details")
        self.assertTrue("Ethernet1_1" not in output)

        self.gscli("interface Ethernet2_1; no switchport mode trunk vlan 1000")
        output = self.gscli("show vlan details")
        self.assertTrue("Ethernet1_1" not in output)

        self.gscli("show vlan details")
        self.gscli("no vlan 1000")
        self.gscli("show vlan details")

    def test_port_breakout(self):
        self.gscli("show vlan details")
        self.gscli("vlan 1000")
        self.gscli("show vlan details")
        self.gscli(
            "interface Ethernet5_1; no shutdown; switchport mode trunk vlan 1000; show",
        )
        self.gscli("show vlan details")

        with self.assertRaises(SSHException):
            self.gscli("interface Ethernet5_1; breakout 4X10GB")

        self.gscli("interface Ethernet5_1; breakout 4X10G")
        # the ds is locked. this must fail
        with self.assertRaises(SSHException):
            self.gscli("interface Ethernet5_1; mtu 4000")

        try:
            self.gscli("show interface brief")
        except SSHException as e:
            pass
        else:
            raise Exception(
                "failed to fail showing interface brief while uSONiC is rebooting"
            )

        for i in range(180):
            try:
                self.gscli("show interface brief")
            except SSHException as e:
                time.sleep(1)
            else:
                print(f"uSONiC took {i}sec to restart")
                break
        else:
            raise Exception("uSONiC didn't come up")

        self.ssh('gscli -c "show interface brief" | grep "Ethernet5_2"')

        # Validating if 'syncd' has come up properly
        validate_str = "sending switch_shutdown_request notification to OA"
        output = self.ssh("kubectl logs deploy/usonic-core syncd")
        self.assertTrue(output.find(validate_str) == -1)

        self.gscli("interface Ethernet5_1; show")
        self.gscli("show interface description")
        self.gscli("show running-config")
        self.gscli("show running-config interface")
        self.gscli("show tech-support")

        with self.assertRaisesRegex(
            SSHException,
            "Invalid",
        ):
            self.gscli("interface Ethernet5_2; speed 100G")

        with self.assertRaisesRegex(
            SSHException,
            "invalid",
        ):
            self.gscli("interface Ethernet5_2; speed 1G")

        self.gscli("interface Ethernet5_3; mtu 9000")

        self.gscli(
            "interface Ethernet5_1; no shutdown"
        )  # add configuration to a sub-interface
        self.gscli(
            "interface Ethernet5_2; no shutdown"
        )  # add configuration to a sub-interface

        self.gscli(
            "interface Ethernet5_1; no shutdown; switchport mode trunk vlan 1000; show",
        )
        self.gscli(
            "interface Ethernet5_3; no shutdown; switchport mode trunk vlan 1000; show",
        )
        self.gscli("show vlan details")

        # Unconfigure
        self.gscli("interface Ethernet5_1; no breakout")

        try:
            self.gscli("show interface brief")
        except SSHException as e:
            pass
        else:
            raise Exception(
                "failed to fail showing interface brief while uSONiC is rebooting"
            )

        for i in range(180):
            try:
                self.gscli("show interface brief")
            except SSHException as e:
                time.sleep(1)
            else:
                print(f"uSONiC took {i}sec to restart")
                break
        else:
            raise Exception("uSONiC didn't come up")

        try:
            self.ssh('gscli -c "show interface brief" | grep "Ethernet5_2"')
        except SSHException as e:
            pass
        else:
            raise Exception("Ethernet5_2 didn't disappear")

        # Validating if 'syncd' has come up properly
        output = self.ssh("kubectl logs deploy/usonic-core syncd")
        self.assertTrue(output.find(validate_str) == -1)

        self.gscli("interface Ethernet5_1; show")
        self.gscli("show interface description")
        self.gscli("show running-config")
        self.gscli("show running-config interface")
        self.gscli("show tech-support")

    def test_fec(self):
        self.gscli("interface Ethernet1_1; no fec")
        output = self.gscli("interface Ethernet1_1; fec fc; show")
        output = "".join(l for l in output.split("\n") if "fec" in l)
        self.assertIn("fc", output)

        with self.assertRaises(SSHException):
            self.gscli("interface Ethernet1_1; fec ff")

    def test_mtu(self):
        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.gscli("interface Ethernet1_1; mtu 56")

        with self.assertRaisesRegex(
            SSHException,
            "Invalid value",
        ):
            self.gscli("interface Ethernet1_1; mtu 110000")

        with self.assertRaisesRegex(
            SSHException,
            "does not satisfy the constraint",
        ):
            self.ssh('gscli -c "interface Ethernet1_1; mtu 10000"')

        output = self.ssh('gscli -c "interface Ethernet1_1; mtu 3500; show" | grep mtu')
        self.assertTrue("3500" in output)

        output = self.ssh('gscli -c "interface Ethernet1_1; no mtu; show" | grep mtu')
        self.assertTrue("9100" in output)

        # check multiple 'no mtu' command won't crash
        self.gscli("interface Ethernet1_1; no mtu")
        self.gscli("interface Ethernet1_1; no mtu")

        output = self.gscli("show datastore /goldstone-interfaces:*")
        self.assertTrue("9100" not in output)
        self.assertTrue("mtu" not in output)

        output = self.gscli(
            "show datastore /goldstone-interfaces:interfaces/interface[name='Ethernet1_1'] operational"
        )
        self.assertTrue("9100" in output)

    def test_speed(self):
        with self.assertRaisesRegex(
            SSHException,
            "ambiguous argument",
        ):
            self.gscli("interface Ethernet1_1; speed 100")

        with self.assertRaisesRegex(
            SSHException,
            "invalid",
        ):
            self.gscli(
                "interface Ethernet1_1; speed 1000000000000000000000000000",
            )

        with self.assertRaisesRegex(
            SSHException,
            "invalid",
        ):
            self.gscli("interface Ethernet1_1; speed 410000")

        with self.assertRaisesRegex(
            SSHException,
            "invalid",
        ):
            self.gscli("interface Ethernet1_1; speed 400000")

        with self.assertRaisesRegex(
            SSHException,
            "Invalid",
        ):
            self.gscli("interface Ethernet1_1; speed 25G")

        output = self.ssh(
            'gscli -c "interface Ethernet1_1; speed 40G; show" | grep speed'
        )
        self.assertTrue("40G" in output)

        output = self.gscli("interface Ethernet1_1; no speed ; show")
        self.assertTrue("100G" in output)

    def test_invalid_intf(self):
        self.gscli("show interface description")

        with self.assertRaisesRegex(
            SSHException,
            "no interface found",
        ):
            self.gscli("interface eth1")

        output = self.gscli("show running-config interface")
        self.assertTrue("eth1" not in output)

        with self.assertRaisesRegex(
            SSHException,
            "no interface found",
        ):
            self.gscli("interface Ethernet79; mtu 4000")

        output = self.gscli("show running-config interface")
        self.assertTrue("Ethernet79" not in output)

        with self.assertRaisesRegex(
            SSHException,
            "no interface found",
        ):
            self.gscli("interface Ethernet111_1")

        output = self.gscli("show running-config interface")
        self.assertTrue("Ethernet111_1" not in output)

    def test_select_intf(self):
        port_num = self.ssh(
            'jq ". | length" /var/lib/goldstone/device/current/usonic/interfaces.json'
        )
        output = self.gscli("interface .*; selected")
        line = output.strip().split("\n")[-1]  # get the last line
        self.assertTrue(
            len(line.split(",")) == int(port_num)
        )  # all interfaces should be selected

        output = self.gscli("interface Ethernet[1-4]_1; selected")
        line = output.strip().split("\n")[-1]  # get the last line
        self.assertTrue(len(line.split(",")) == 4)  # 4 interfaces should be selected

        # invalid regex
        with self.assertRaisesRegex(
            SSHException,
            "failed to compile",
        ):
            output = self.gscli("interface Ethernet[1-4_1; selected")

    def test_statistics(self):
        with self.assertRaisesRegex(
            SSHException,
            "Invalid interface",
        ):
            self.gscli("show interface counters Ethernet1_1 Ethernet2_2")

        output = self.gscli("show interface counters Ethernet1_1 Ethernet2_1")
        self.assertTrue("Ethernet1_1" in output)
        self.assertTrue("Ethernet2_1" in output)

        output = self.gscli("show interface counters")
        # Validataing if last interface is present
        self.assertTrue("Ethernet20_1" in output)

        output = self.gscli("clear interface counters")
        self.assertTrue("Interface counters are cleared" in output)


class TestSouthTAI(TestBase):
    def test_tai(self):
        output = self.gscli("show transponder summary")
        lines = [line for line in output.split("\n") if "piu" in line]

        self.assertTrue(len(lines) != 0)

        for line in lines:
            elems = [e.strip() for e in line.split("|") if e]
            if elems[1] != "N/A":
                device = elems[0]
                break
        else:
            raise Exception("no transponder found on this device")

        self.gscli(f"transponder {device}; netif 0; show")
        self.gscli(f"transponder {device}; netif 0; tx-laser-freq 194.5thz")
        self.gscli(f"transponder {device}; netif 0; show")

        with self.assertRaisesRegex(SSHException, "invalid frequency input"):
            self.gscli(f"transponder {device}; netif 0; tx-laser-freq aaa")

        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; output-power -4; show" | grep output-power',
        )
        self.assertTrue("-4.00 dBm" in output)
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; no output-power; show" | grep output-power',
        )
        self.assertTrue("0.00 dBm" in output)

        #    output = ssh(
        #        cli,
        #        f'gscli -c "transponder {device}; netif 0; voa-rx 0.9; show" | grep voa-rx',
        #    )
        #    assert "0.9" in output
        #    output = ssh(
        #        cli,
        #        f'gscli -c "transponder {device}; netif 0; no voa-rx; show" | grep voa-rx',
        #    )
        #    assert "0.0" in output

        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz; show" | grep tx-laser-freq',
        )
        self.assertTrue("193.70THz" in output)
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; no tx-laser-freq; show" | grep tx-laser-freq',
        )
        self.assertTrue("193.50THz" in output)

        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk; show" | grep modulation-format',
        )
        self.assertTrue("dp-qpsk" in output)
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; no modulation-format; show" | grep modulation-format',
        )
        self.assertTrue("dp-16-qam" in output)

        #    ssh(cli, f'gscli -c "transponder {device}; netif 0; voa-rx 0.9"')
        self.gscli(f"transponder {device}; netif 0; output-power -3.2")
        self.gscli(f"transponder {device}; netif 0; tx-laser-freq 193.7thz")
        self.gscli(f"transponder {device}; netif 0; modulation-format dp-qpsk")

        self.ssh("kubectl rollout restart ds/south-tai")
        check_pod(self.cli, "south-tai")

        #    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" | grep voa-rx')
        #    assert "0.9" in output
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; show" | grep output-power'
        )
        self.assertTrue("-3.20 dBm" in output)
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; show" | grep tx-laser-freq'
        )
        self.assertTrue("193.70THz" in output)
        output = self.ssh(
            f'gscli -c "transponder {device}; netif 0; show" | grep modulation-format'
        )
        self.assertTrue("dp-qpsk" in output)

        self.gscli(f"transponder {device}; shutdown")
        self.gscli(f"transponder {device}; no shutdown")
        self.gscli("clear datastore goldstone-transponder")


def test_tacacs(host, cli):

    # Configuring first TACACS+ server details
    output = ssh(
        cli, 'gscli -c "tacacs-server host 192.168.208.100 key testkey123; show tacacs"'
    )
    assert "192.168.208.100" in output
    assert "testkey123" in output
    assert "49" in output
    assert "300" in output

    # checking port number value validation
    try:
        ssh(
            cli,
            'gscli -c "tacacs-server host 192.168.208.101 key testkey123 port number"',
        )
    except SSHException as e:
        assert "invalid value" in e.stderr

    # checking timeout value validation
    try:
        ssh(
            cli,
            'gscli -c "tacacs-server host 192.168.208.101 key testkey123 timeout seconds"',
        )
    except SSHException as e:
        assert "invalid value" in e.stderr

    # checking port number value and timeout validation
    try:
        ssh(
            cli,
            'gscli -c "tacacs-server host 192.168.208.101 key testkey123 port number timeout seconds"',
        )
    except SSHException as e:
        assert "invalid value" in e.stderr

    # Configuring second TACACS+ server details
    output = ssh(
        cli,
        'gscli -c "tacacs-server host 192.168.208.101 key testkey123 port 42; show tacacs"',
    )
    assert "192.168.208.101" in output
    assert "testkey123" in output
    assert "42" in output
    assert "300" in output

    # Configuring third TACACS+ server details
    output = ssh(
        cli,
        'gscli -c "tacacs-server host 192.168.208.102 key testing123 port 49 timeout 180; show tacacs"',
    )
    assert "192.168.208.102" in output
    assert "testing123" in output
    assert "49" in output
    assert "180" in output

    # setting aaa authentication to tacacs
    output = ssh(
        cli, 'gscli -c "aaa authentication login default group tacacs; show aaa"'
    )
    assert "tacacs" in output

    # login using tacacs username and password
    with paramiko.SSHClient() as cli_tacacs:
        cli_tacacs.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli_tacacs.connect(host, username="gs_user1", password="goldstone1")

        output = ssh(cli_tacacs, "show aaa")
        assert "tacacs" in output

    # setting aaa authentication to local
    output = ssh(cli, 'gscli -c "aaa authentication login default local; show aaa"')
    assert "local" in output

    # Unconfigure
    output = ssh(cli, 'gscli -c "no aaa authentication login"')
    assert "local" not in output
    output = ssh(cli, 'gscli -c "no tacacs-server host 192.168.208.102"')
    assert "192.168.208.102" not in output
    output = ssh(cli, 'gscli -c "no tacacs-server host 192.168.208.101"')
    assert "192.168.208.101" not in output
    output = ssh(cli, 'gscli -c "no tacacs-server host 192.168.208.100"')
    assert "192.168.208.100" not in output


if __name__ == "__main__":
    unittest.main()
