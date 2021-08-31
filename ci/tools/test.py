#!/usr/bin/env python3

import paramiko
import argparse
import time
import sys

from .common import *


def test_system(cli):
    ssh(cli, 'gscli -c "show version"')


def test_vlan(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 2000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan range 1000-1010"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan range 200-205,250,295-300"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan range 200-205,250"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 2000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "show interface brief"')
    ssh(cli, 'gscli -c "show interface description"')
    ssh(cli, 'gscli -c "show tech-support"')
    ssh(cli, 'gscli -c "show running-config"')
    ssh(cli, 'gscli -c "show running-config interface"')
    ssh(cli, 'gscli -c "show running-config vlan"')
    try:
        ssh(cli, 'gscli -c "vlan range 25-19"')
    except SSHException as e:
        assert "The vlan-range entered is invalid" in e.stderr


def test_auto_nego(cli):
    ssh(cli, 'gscli -c "interface Ethernet3_1; auto-negotiate enable"')
    ssh(cli, 'gscli -c "interface Ethernet3_1; auto-negotiate disable"')

    ssh(cli, 'gscli -c "interface Ethernet3_1; auto-negotiate enable"')
    ssh(cli, "kubectl rollout restart ds/gs-mgmt-sonic")
    check_pod(cli, "gs-mgmt-sonic")
    time.sleep(90)
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "auto-negotiate enable" in output
    ssh(cli, 'gscli -c "interface Ethernet3_1; no auto-negotiate"')
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "auto-negotiate" not in output
    ssh(cli, 'gscli -c "interface Ethernet3_1; auto-negotiate enable"')
    try:
        ssh(cli, 'gscli -c "interface Ethernet3_1; interface-type SR4"')
    except SSHException as e:
        assert "../../auto-negotiate/config/enabled = 'false'" in e.stderr
    else:
        raise Exception(
            "Failed to stop configuring interface type when auto-nego is enabled"
        )
    try:
        ssh(cli, 'gscli -c "interface Ethernet3_1; fec rs"')
    except SSHException as e:
        assert "../../auto-negotiate/config/enabled = 'false'" in e.stderr
    else:
        raise Exception("Failed to stop configuring FEC when auto-nego is enabled")
    try:
        ssh(cli, 'gscli -c "interface Ethernet3_1; speed 40G"')
    except SSHException as e:
        assert "../../auto-negotiate/config/enabled = 'false'" in e.stderr
    else:
        raise Exception("Failed to stop configuring speed when auto-nego is enabled")

    ssh(cli, 'gscli -c "interface Ethernet3_1; auto-negotiate advertise 40G"')
    output = ssh(cli, 'gscli -c "interface Ethernet3_1; show" | grep advertise')


def test_intf_type(cli):
    ssh(cli, 'gscli -c "interface Ethernet1_1; interface-type SR4"')
    ssh(cli, 'gscli -c "interface Ethernet1_1; interface-type KR4"')

    ssh(cli, 'gscli -c "interface Ethernet1_1; interface-type CR4"')
    ssh(cli, "kubectl rollout restart ds/gs-mgmt-sonic")
    check_pod(cli, "gs-mgmt-sonic")
    time.sleep(90)
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "interface-type CR4" in output
    ssh(cli, 'gscli -c "interface Ethernet1_1; no interface-type"')
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "interface-type" not in output


def test_speed_intftype(cli):
    try:
        ssh(cli, 'gscli -c "interface Ethernet4_1; speed 10000"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    try:
        ssh(cli, 'gscli -c "interface Ethernet4_1; interface-type SR"')
    except SSHException as e:
        assert "Unsupported interface type" in e.stderr


def test_ufd(cli):
    ssh(cli, 'gscli -c "ufd ufd1"')
    ssh(cli, 'gscli -c "interface Ethernet1_1; ufd ufd1 uplink"')
    ssh(cli, 'gscli -c "interface Ethernet2_1; ufd ufd1 downlink"')
    ssh(cli, 'gscli -c "interface Ethernet4_1; ufd ufd1 downlink"')
    output = ssh(cli, 'gscli -c "ufd ufd1; show"')
    assert "Ethernet1_1" in output
    assert "Ethernet2_1" in output
    assert "Ethernet4_1" in output

    try:
        ssh(cli, 'gscli -c "interface Ethernet5_1; ufd ufd1 uplink"')
    except SSHException as e:
        assert "Uplink Already configured" in e.stderr
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; ufd ufd1 downlink"')
    except SSHException as e:
        assert "Ethernet1_1:Port Already configured" in e.stderr

    ssh(cli, 'gscli -c "ufd 10"')
    ssh(cli, 'gscli -c "interface Ethernet6_1; ufd 10 uplink"')
    ssh(cli, 'gscli -c "interface Ethernet7_1; ufd 10 downlink"')
    ssh(cli, 'gscli -c "interface Ethernet6_1; shutdown"')
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet7_1  |   dormant  " in output
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "ufd 10 downlink" in output


def test_portchannel(cli):
    ssh(cli, 'gscli -c "portchannel PortChannel10"')
    ssh(cli, 'gscli -c "interface Ethernet1_1; portchannel PortChannel10"')
    ssh(cli, 'gscli -c "interface Ethernet2_1; portchannel PortChannel10"')
    ssh(cli, 'gscli -c "interface Ethernet4_1; portchannel PortChannel10"')
    output = ssh(cli, 'gscli -c "portchannel PortChannel10; show"')
    assert "Ethernet1_1" in output
    assert "Ethernet2_1" in output
    assert "Ethernet4_1" in output
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "portchannel PortChannel10" in output
    ssh(cli, 'gscli -c "portchannel PortChannel20"')
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; portchannel PortChannel10"')
    except SSHException as e:
        assert "Invalid argument: User callback failed" in e.stderr
    ssh(cli, 'gscli -c "portchannel PortChannel9"')
    ssh(cli, 'gscli -c "portchannel PortChannel99"')
    ssh(cli, 'gscli -c "portchannel PortChannel999"')
    ssh(cli, 'gscli -c "portchannel PortChannel9999"')
    try:
        ssh(cli, 'gscli -c "portchannel PortChannel10000"')
    except SSHException as e:
        assert (
            'Value "PortChannel10000" does not satisfy the constraint "PortChannel[0-9]{1,4}"'
            in e.stderr
        )
    try:
        ssh(cli, 'gscli -c "portchannel Lag10"')
    except SSHException as e:
        assert (
            'Value "Lag10" does not satisfy the constraint "PortChannel[0-9]{1,4}"'
            in e.stderr
        )
    ssh(cli, 'gscli -c "interface Ethernet10_1; portchannel PortChannel9"')
    output = ssh(cli, "ip link | grep -w PortChannel9")
    assert "PortChannel9" in output
    output = ssh(
        cli, "kubectl exec -t usonic-cli -- show interface status|grep Ethernet10_1"
    )
    assert "PortChannel9" in output
    ssh(cli, 'gscli -c "interface Ethernet10_1; no portchannel PortChannel9"')
    output = ssh(
        cli, "kubectl exec -t usonic-cli -- show interface status|grep Ethernet10_1"
    )
    try:
        assert "PortChannel9" in output
        raise Exception("Can't unconfigure interface from Portchannel")
    except AssertionError:
        print(
            "This is negative case of unconfiguration of an interface from a portchannel"
        )
    ssh(cli, 'gscli -c "portchannel PortChannel9; shutdown"')
    ssh(cli, 'gscli -c "portchannel PortChannel9; no shutdown"')
    ssh(cli, 'gscli -c "no portchannel PortChannel9"')
    try:
        ssh(cli, "ip link | grep -w PortChannel9")
        raise Exception("Can't unconfigure Portchannel")
    except SSHException:
        print("This is negative case of unconfiguration of a portchannel")


def test_tai(cli):
    output = ssh(cli, 'gscli -c "show transponder summary"')
    lines = [line for line in output.split() if "piu" in line]

    if len(lines) == 0:
        raise Exception("no transponder found on this device")

    elems = [elem for elem in lines[0].split("|") if "piu" in elem]
    if len(elems) == 0:
        raise Exception(f"invalid output: {output}")

    device = elems[0].strip()

    ssh(cli, f'gscli -c "transponder {device}; netif 0; show"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq 194.5thz"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; show"')

    try:
        ssh(cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq aaa"')
    except SSHException as e:
        assert "invalid frequency input" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: tx-laser-freq aaa")

    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; output-power -4; !sleep 1; show" | grep output-power',
    )
    assert "-4.00 dBm" in output
    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; no output-power; !sleep 1; show" | grep output-power',
    )
    assert "0.00 dBm" in output

    #    output = ssh(
    #        cli,
    #        f'gscli -c "transponder {device}; netif 0; voa-rx 0.9; !sleep 1; show" | grep voa-rx',
    #    )
    #    assert "0.9" in output
    #    output = ssh(
    #        cli,
    #        f'gscli -c "transponder {device}; netif 0; no voa-rx; !sleep 1; show" | grep voa-rx',
    #    )
    #    assert "0.0" in output

    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz; !sleep 1; show" | grep tx-laser-freq',
    )
    assert "193.70THz" in output
    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; no tx-laser-freq; !sleep 1; show" | grep tx-laser-freq',
    )
    assert "193.50THz" in output

    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk; !sleep 1; show" | grep modulation-format',
    )
    assert "dp-qpsk" in output
    output = ssh(
        cli,
        f'gscli -c "transponder {device}; netif 0; no modulation-format; !sleep 1; show" | grep modulation-format',
    )
    assert "dp-16-qam" in output

    #    ssh(cli, f'gscli -c "transponder {device}; netif 0; voa-rx 0.9"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; output-power -3.2"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk"')

    ssh(cli, "kubectl rollout restart ds/gs-mgmt-tai")
    check_pod(cli, "gs-mgmt-tai")

    #    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" | grep voa-rx')
    #    assert "0.9" in output
    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; show" | grep output-power'
    )
    assert "-3.20 dBm" in output
    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; show" | grep tx-laser-freq'
    )
    assert "193.70THz" in output
    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; show" | grep modulation-format'
    )
    assert "dp-qpsk" in output

    ssh(cli, f'gscli -c "transponder {device}; shutdown"')
    ssh(cli, f'gscli -c "transponder {device}; no shutdown"')
    ssh(cli, f'gscli -c "clear datastore goldstone-tai"')


def test_vlan_member_add_delete(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(
        cli,
        'gscli -c "interface Ethernet1_1; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(
        cli,
        'gscli -c "interface Ethernet2_1; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(
        cli,
        'gscli -c "interface Ethernet1_1; no shutdown; no switchport mode trunk vlan 1000; show"',
    )
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; switchport mode trunk vlab 1000"')
    except SSHException as e:
        assert "usage: switchport mode (trunk|access) vlan <vid>" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd switchport mode trunk vlab 1000"
        )
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; switchport mode trunk access 1000"')
    except SSHException as e:
        assert "usage: switchport mode (trunk|access) vlan <vid>" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd switchport mode trunk access 1000"
        )

    ssh(cli, 'gscli -c "interface Ethernet1_1; switchport mode trunk vlan 1000"')
    output = ssh(cli, 'gscli -c "show vlan details"')
    assert "Ethernet1_1" in output
    #    try:
    #        ssh(
    #            cli, 'gscli -c "interface Ethernet1_1; no switchport mode access vlan 1000"'
    #        )
    #    except SSHException as e:
    #        assert "Incorrect mode given" in e.stderr
    #    else:
    #        raise Exception(
    #            "failed to fail with an invalid cmd no switchport mode access vlan 1000"
    #        )
    try:
        ssh(
            cli,
            'gscli -c "interface Ethernet1_1; no switchport mode trunk access 1000"',
        )
    except SSHException as e:
        assert "usage : no switchport mode trunk|access vlan <vid>" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd no switchport mode trunk access 1000"
        )

    ssh(cli, 'gscli -c "interface Ethernet1_1; no switchport mode trunk vlan 1000"')
    output = ssh(cli, 'gscli -c "show vlan details"')
    assert "Ethernet1_1" not in output

    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')


def test_port_breakout(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(
        cli,
        'gscli -c "interface Ethernet5_1; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(cli, 'gscli -c "show vlan details"')

    try:
        ssh(cli, 'gscli -c "interface Ethernet5_1; breakout 4X10GB"')
    except:
        print("This was 'Negative Testcase' for Breakout configuration")

    ssh(cli, 'gscli -c "interface Ethernet5_1; breakout 4X10G"')
    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")

    # the ds is locked. this must fail
    try:
        ssh(cli, 'gscli -c "interface Ethernet5_1; mtu 4000"')
    except SSHException as e:
        assert "uSONiC is rebooting" in e.stderr or "locked" in e.stderr
    else:
        raise Exception("failed to fail mtu setting under ds locked")

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" not in output

    for i in range(180):
        try:
            ssh(cli, 'gscli -c "show interface brief" | grep Ethernet5_2')
        except SSHException as e:
            time.sleep(1)
        else:
            print(f"uSONiC took {i}sec to restart")
            break
    else:
        raise Exception("Ethernet5_2 didn't appear")

    # Validating if 'syncd' has come up properly
    validate_str = "sending switch_shutdown_request notification to OA"
    output = ssh(cli, "kubectl logs deploy/usonic-core syncd")
    if output.find(validate_str) == -1:
        print("Syncd in usonic has come up properly")
    else:
        print("Syncd in usonic has ERRORS")
        sys.exit(1)

    ssh(cli, 'gscli -c "interface Ethernet5_1; show"')
    ssh(cli, 'gscli -c "show interface description"')
    ssh(cli, 'gscli -c "show running-config"')
    ssh(cli, 'gscli -c "show running-config interface"')
    ssh(cli, 'gscli -c "show tech-support"')
    try:
        ssh(cli, 'gscli -c "interface Ethernet5_2; speed 100G"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 100G")
    try:
        ssh(cli, 'gscli -c "interface Ethernet5_2; speed 1G"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 1G")

    ssh(cli, 'gscli -c "interface Ethernet5_3; mtu 9000"')

    ssh(
        cli, 'gscli -c "interface Ethernet5_1; no shutdown"'
    )  # add configuration to a sub-interface
    ssh(
        cli, 'gscli -c "interface Ethernet5_2; no shutdown"'
    )  # add configuration to a sub-interface

    ssh(
        cli,
        'gscli -c "interface Ethernet5_1; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(
        cli,
        'gscli -c "interface Ethernet5_3; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(cli, 'gscli -c "show vlan details"')

    # Unconfigure
    ssh(cli, 'gscli -c "interface Ethernet5_1; no breakout"')

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" in output

    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")
    for i in range(180):
        try:
            ssh(cli, 'gscli -c "show interface brief" | grep Ethernet5_2')
        except SSHException as e:
            print(f"uSONiC took {i}sec to restart")
            break
        else:
            time.sleep(1)
    else:
        raise Exception("Ethernet5_2 didn't disappear")

    # Validating if 'syncd' has come up properly
    output = ssh(cli, "kubectl logs deploy/usonic-core syncd")
    if output.find(validate_str) == -1:
        print("Syncd in usonic has come up properly")
    else:
        print("Syncd in usonic has ERRORS")
        sys.exit(1)

    ssh(cli, 'gscli -c "interface Ethernet5_1; show"')
    ssh(cli, 'gscli -c "show interface description"')
    ssh(cli, 'gscli -c "show running-config"')
    ssh(cli, 'gscli -c "show running-config interface"')
    ssh(cli, 'gscli -c "show tech-support"')


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
        assert "Invalid value" in e.stderr

    # checking timeout value validation
    try:
        ssh(
            cli,
            'gscli -c "tacacs-server host 192.168.208.101 key testkey123 timeout seconds"',
        )
    except SSHException as e:
        assert "Invalid value" in e.stderr

    # checking port number value and timeout validation
    try:
        ssh(
            cli,
            'gscli -c "tacacs-server host 192.168.208.101 key testkey123 port number timeout seconds"',
        )
    except SSHException as e:
        assert "Invalid value" in e.stderr

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


def test_logging(cli):
    ssh(cli, 'gscli -c "show logging"')
    ssh(cli, 'gscli -c "show logging 50"')
    ssh(cli, 'gscli -c "show logging sonic 50"')
    ssh(cli, 'gscli -c "show logging sonic"')
    ssh(cli, 'gscli -c "show logging onlp 100"')
    try:
        ssh(cli, 'gscli -c "show logging h01"')
    except SSHException as e:
        assert "show logging [sonic|tai|onlp|] [<num_lines>|]" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: show logging h01")


def test_fec(cli):
    output = ssh(cli, 'gscli -c "interface Ethernet1_1; fec fc; show" | grep fec')
    assert "fc" in output

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; fec fc; show" | grep fec')
    assert "fc" in output

    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; fec ff"')
    except SSHException as e:
        assert "usages: fec <fc|rs>" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: fec ff")


def test_mtu(cli):
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; mtu 56"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: mtu 56")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; mtu 110000"')
    except SSHException as e:
        assert "Invalid value" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: mtu 110000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; mtu 10000"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: mtu 10000")
    output = ssh(cli, 'gscli -c "interface Ethernet1_1; mtu 3500; show" | grep mtu')
    assert "3500" in output

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu; show" | grep mtu')
    assert "9100" in output

    # check multiple 'no mtu' command won't crash
    ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu"')
    ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu"')

    output = ssh(cli, 'gscli -c "show datastore /goldstone-interfaces:*"')
    assert "9100" not in output
    assert "mtu" not in output

    output = ssh(
        cli,
        "gscli -c \"show datastore /goldstone-interfaces:interfaces/interface[name='Ethernet1_1'] operational\"",
    )
    assert "9100" in output
    assert "ipv4" in output


def test_speed(cli):
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 100"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 100")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 1000000000000000000000000000"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid command: speed 1000000000000000000000000000"
        )
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 410000"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 410000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 400000"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 400000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 25G"')
    except SSHException as e:
        assert "Invalid" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 25G")

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; speed 40G; show" | grep speed')
    assert "40G" in output

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; no speed ; !sleep 1; show"')
    assert "100G" in output


def test_invalid_intf(cli):
    ssh(cli, 'gscli -c "show interface description"')
    try:
        ssh(cli, 'gscli -c "interface eth1"')
    except SSHException as e:
        assert "no interface found" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: interface eth1")

    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "eth1" not in output
    try:
        ssh(cli, 'gscli -c "interface Ethernet79; mtu 4000"')
    except SSHException as e:
        assert "no interface found" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: interface Ethernet79")
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "Ethernet79" not in output
    try:
        ssh(cli, 'gscli -c "interface Ethernet111_1"')
    except SSHException as e:
        assert "no interface found" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid command: interface Ethernet111_1"
        )
    output = ssh(cli, 'gscli -c "show running-config interface"')
    assert "Ethernet111_1" not in output


def test_mgmt_intf(cli):
    ssh(cli, 'gscli -c "show arp"')
    ssh(cli, 'gscli -c "ping 10.10.10.250 -c 4"')
    output = ssh(cli, 'gscli -c "show arp"')
    assert "10.10.10.250" in output
    ssh(cli, 'gscli -c "clear arp"')
    output = ssh(cli, 'gscli -c "show arp"')
    assert "10.10.10.250" not in output
    ssh(cli, 'gscli -c "show arp"')
    ssh(cli, 'gscli -c "ping 10.10.10.100 -c 4"')
    output = ssh(cli, 'gscli -c "show arp"')
    assert "10.10.10.100" in output
    ssh(cli, 'gscli -c "clear arp"')
    ssh(cli, 'gscli -c "clear arp"')
    output = ssh(cli, 'gscli -c "show arp"')
    assert "10.10.10.100" not in output


def test_select_intf(cli):
    port_num = ssh(
        cli, 'jq ". | length" /var/lib/goldstone/device/current/usonic/interfaces.json'
    )
    output = ssh(cli, 'gscli -c "interface .*; selected"')
    line = output.strip().split("\n")[-1]  # get the last line
    assert len(line.split(",")) == int(port_num)  # all interfaces should be selected

    output = ssh(cli, 'gscli -c "interface Ethernet[1-4]_1; selected"')
    line = output.strip().split("\n")[-1]  # get the last line
    assert len(line.split(",")) == 4  # 4 interfaces should be selected

    # invalid regex
    try:
        output = ssh(cli, 'gscli -c "interface Ethernet[1-4_1; selected"')
    except SSHException as e:
        assert "failed to compile" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid command: interface Ethernet[1-4_1"
        )


def test_statistics(cli):
    try:
        ssh(cli, 'gscli -c "show interface counters Ethernet1_1 Ethernet2_2"')
    except SSHException as e:
        assert "Invalid interface" in e.stderr
    else:
        raise Exception("failed to fail with an invalid interface Ethernet2_2")

    output = ssh(cli, 'gscli -c "show interface counters Ethernet1_1 Ethernet2_1"')
    assert "Ethernet1_1" in output
    assert "Ethernet2_1" in output

    output = ssh(cli, 'gscli -c "show interface counters"')
    # Validataing if last interface is present
    assert "Ethernet20_1" in output

    output = ssh(cli, 'gscli -c "clear interface counters"')
    assert "Interface counters are cleared" in output


def test_mgmt_if_cmds(cli):
    try:
        ssh(cli, 'gscli -c "management-interface eth0; ip address 999.999.999.999/24"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd ip address 999.999.999.999/24"
        )
    try:
        ssh(cli, 'gscli -c "management-interface eth0; ip address 999.999.999.999.24"')
    except SSHException as e:
        assert (
            "Entered address is not in the expected format - A.B.C.D/<mask>" in e.stderr
        )
    else:
        raise Exception(
            "failed to fail with an invalid cmd ip address 999.999.999.999/24"
        )
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip address 20.20.20.0/24; show running-config mgmt-if"',
    )
    assert "ip address 20.20.20.0/24" in output

    try:
        ssh(
            cli,
            'gscli -c "management-interface eth0; no ip address 999.999.999.999/24"',
        )
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd no ip address 999.999.999.999/24"
        )
    try:
        ssh(cli, 'gscli -c "management-interface eth0; ip address 999.999.999.999.24"')
    except SSHException as e:
        assert (
            "Entered address is not in the expected format - A.B.C.D/<mask>" in e.stderr
        )
    else:
        raise Exception(
            "failed to fail with an invalid cmd no ip address 999.999.999.999.24"
        )
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip address 20.20.20.0/24; show running-config mgmt-if"',
    )
    assert "ip address 20.20.20.0/24" not in output

    try:
        ssh(cli, 'gscli -c "management-interface eth0; ip route 10.10.10.117"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid cmd ip route 10.10.10.117")
    try:
        ssh(cli, 'gscli -c "management-interface eth0; ip route 10.10.10.117/35"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid cmd ip route 10.10.10.117/35")
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 30.30.30.0/24; show running-config mgmt-if"',
    )
    assert "ip route 30.30.30.0/24" in output

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.30.30.0/24" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip route 30.30.30.0/24; show running-config mgmt-if"',
    )
    assert "ip route 30.30.30.0/24" not in output

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.30.30.0/24" not in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 30.20.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 30.20.0.0/16" in output
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 20.10.20.0/24; show running-config mgmt-if"',
    )
    assert "ip route 20.10.20.0/24" in output
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 30.20.20.0/24; show running-config mgmt-if"',
    )
    assert "ip route 30.20.20.0/24" in output
    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.20.0.0/16" in output
    assert "20.10.20.0/24" in output
    assert "30.20.20.0/24" in output

    ssh(cli, 'gscli -c "clear ip route"')

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.20.0.0/16" not in output
    assert "20.10.20.0/24" not in output
    assert "30.20.20.0/24" not in output


def test_platform(cli):
    # ADD test for platform CLIs here
    output = ssh(cli, 'gscli -c "show datastore /goldstone-platform:* operational"')
    assert "piu" in output
    assert "transceiver" in output
    print("Component PIU and SFP found in operational-DB")
    ssh(cli, 'gscli -c "show chassis-hardware fan"')
    ssh(cli, 'gscli -c "show chassis-hardware led"')
    ssh(cli, 'gscli -c "show chassis-hardware psu"')
    ssh(cli, 'gscli -c "show chassis-hardware thermal"')
    ssh(cli, 'gscli -c "show chassis-hardware system"')
    ssh(cli, 'gscli -c "show chassis-hardware transceiver table"')
    ssh(cli, 'gscli -c "show chassis-hardware transceiver"')
    ssh(cli, 'gscli -c "show chassis-hardware piu table"')
    output = ssh(cli, 'gscli -c "show chassis-hardware piu"')
    assert "piu" in output
    assert "PRESENT" in output
    output = ssh(cli, 'gscli -c "show tech-support"')
    assert "FAN INFORMATION" in output


def test_system_reconcile(cli):
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 31.21.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 31.21.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip address 20.21.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 20.21.0.0/16" in output

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "31.21.0.0/16" in output

    ssh(cli, "systemctl restart gs-south-system")
    time.sleep(10)

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "31.21.0.0/16" in output
    output = ssh(cli, 'gscli -c "show running-config mgmt-if"')
    assert "ip address 20.21.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip route 31.21.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 31.21.0.0/16" not in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip address 20.21.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 20.21.0.0/16" not in output

    # case for saving a tree without leaf address
    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip address 56.10.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 56.10.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip address 56.10.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 56.10.0.0/16" not in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 100.17.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 100.17.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip route 100.17.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 100.17.0.0/16" not in output

    ssh(cli, "systemctl restart gs-south-system")
    time.sleep(10)

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip address 56.10.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 56.10.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip address 56.10.0.0/16; show running-config mgmt-if"',
    )
    assert "ip address 56.10.0.0/16" not in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; ip route 100.17.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 100.17.0.0/16" in output

    output = ssh(
        cli,
        'gscli -c "management-interface eth0; no ip route 100.17.0.0/16; show running-config mgmt-if"',
    )
    assert "ip route 100.17.0.0/16" not in output


def test_subcommands(cli):
    output = ssh(cli, 'gscli -c "show transponder summary"')
    lines = [line for line in output.split() if "piu" in line]

    if len(lines) == 0:
        raise Exception("no transponder found on this device")

    elems = [elem for elem in lines[0].split("|") if "piu" in elem]
    if len(elems) == 0:
        raise Exception(f"invalid output: {output}")
    output = ssh(cli, 'gscli -c "show interface counters Ethernet1_1"')
    assert "Ethernet1_1" in output
    ssh(cli, 'gscli -c "show interface brief"')
    ssh(cli, 'gscli -c "show interface description"')


def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        try:
            test_system(cli)
            test_logging(cli)
            #    test_tacacs(host, cli)
            test_mgmt_intf(cli)
            test_mgmt_if_cmds(cli)
            test_system_reconcile(cli)
        except Exception as e:
            ssh(cli, "systemctl status gs-south-system.service")
            ssh(cli, "journalctl -u gs-south-system.service")
            raise e

        try:
            ssh(cli, "kubectl exec -t deploy/tai -- taish -c 'log-level debug'")
            test_tai(cli)
            test_subcommands(cli)
        except Exception as e:
            ssh(cli, "kubectl get pods -A")
            ssh(cli, "kubectl logs -l app=gs-mgmt-tai")
            ssh(cli, "kubectl logs deploy/tai")
            raise e
        finally:
            ssh(cli, "kubectl exec -t deploy/tai -- taish -c 'log-level info'")

        try:
            test_vlan(cli)
            test_mtu(cli)
            test_speed(cli)
            test_invalid_intf(cli)
            test_select_intf(cli)
            test_statistics(cli)
            test_vlan_member_add_delete(cli)
            test_auto_nego(cli)
            test_intf_type(cli)
            test_speed_intftype(cli)
            test_ufd(cli)
            test_portchannel(cli)
            test_port_breakout(cli)
        except Exception as e:
            ssh(cli, "kubectl get pods -A")
            ssh(cli, "kubectl logs -l app=gs-mgmt-sonic")
            ssh(cli, "kubectl describe pods -l app=gs-mgmt-sonic")
            raise e

        try:
            test_platform(cli)
        except Exception as e:
            ssh(cli, "kubectl get pods -A")
            ssh(cli, "kubectl logs -l app=gs-mgmt-onlp")
            ssh(cli, "kubectl describe pods -l app=gs-mgmt-onlp")
            raise e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone CI tool")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
