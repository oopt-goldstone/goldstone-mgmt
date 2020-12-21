#!/usr/bin/env python3

import paramiko
import argparse
import subprocess
import sys
from scp import SCPClient
import time
import os


class SSHException(Exception):
    def __init__(self, msg, ret, stdout, stderr):
        super().__init__(msg)
        self.ret = ret
        self.stdout = stdout
        self.stderr = stderr


def ssh(cli, cmd):
    print(f'ssh: "{cmd}"')
    _, stdout, stderr = cli.exec_command(cmd)
    output = []
    err = []
    for line in stdout:
        output.append(line)
        print(f"stdout: {line}", end="")
    for line in stderr:
        err.append(line)
        print(f"stderr: {line}", end="")
    ret = stdout.channel.recv_exit_status()
    if ret != 0:
        raise SSHException(
            f"{cmd} failed: ret: {ret}", ret, "".join(output), "".join(err)
        )

    return "".join(output)


def run(cmd):
    print(f'run: "{cmd}"')
    subprocess.run(
        cmd,
        shell=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
        env=os.environ,
    )


def test_system(cli):
    ssh(cli, 'gscli -c "show version"')


def test_vlan(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 2000"')
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


def test_tai(cli):
    output = ssh(cli, 'gscli -c "show transponder summary"')
    lines = [line for line in output.split() if "/dev" in line]

    if len(lines) == 0:
        raise Exception("no transponder found on this device")

    elems = [elem for elem in lines[0].split("|") if "/dev" in elem]
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
        cli, f'gscli -c "transponder {device}; netif 0; output-power -1; show"'
    )
    assert "-1" in output
    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; no output-power; show"'
    )
    assert "1" in output

    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; voa-rx 2; show"')
    assert "2" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no voa-rx; show"')
    assert "0" in output

    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz; show"'
    )
    assert "193.70THz" in output
    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; no tx-laser-freq; show"'
    )
    assert "193.50THz" in output

    output = ssh(
        cli, f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk"'
    )
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" ')
    assert "dp-qpsk" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no modulation-format"')
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" ')
    assert "dp-16-qam" in output

    ssh(cli, f'gscli -c "transponder {device}; netif 0; voa-rx 2.3"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; output-power -1.2"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz"')
    ssh(cli, f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk"')

    ssh(cli, "kubectl rollout restart ds/gs-mgmt-tai")
    time.sleep(15)
    pod = ssh(cli, "kubectl get pod -l app=gs-mgmt-tai -o jsonpath='{.items[0].metadata.name}'")
    ssh(cli, f"kubectl wait --timeout=90s --for=condition=ready pod/{pod}")
    ssh(cli, "kubectl get pods")

    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show"')
    assert "2.3" in output
    assert "-1.2" in output
    assert "193.70THz" in output
    assert "dp-qpsk" in output

    ssh(cli, f'gscli -c "transponder {device}; shutdown"')
    ssh(cli, f'gscli -c "transponder {device}; no shutdown"')


def test_vlan_member_add_delete(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(
        cli,
        'gscli -c "interface Ethernet1_1; no shutdown; switchport mode trunk vlan 1000; show"',
    )
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')


def test_port_breakout(cli):
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
        assert "is locked" in e.stderr
    else:
        raise Exception("failed to fail mtu setting under ds locked")

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" not in output

    for i in range(90):
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
    output = ssh(cli, "kubectl logs deploy/usonic syncd")
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
        ssh(cli, 'gscli -c "interface Ethernet5_2; speed 10000"')
    except SSHException as e:
        assert "Invalid argument" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 10000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet5_2; speed 1000"')
    except SSHException as e:
        assert "Invalid argument" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 1000")

    ssh(
        cli, 'gscli -c "interface Ethernet5_1; no shutdown"'
    )  # add configuration to a sub-interface
    ssh(
        cli, 'gscli -c "interface Ethernet5_2; no shutdown"'
    )  # add configuration to a sub-interface

    # Unconfigure
    ssh(cli, 'gscli -c "interface Ethernet5_1; no breakout"')

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" in output

    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")
    for i in range(90):
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
    output = ssh(cli, "kubectl logs deploy/usonic syncd")
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
    output = ssh(cli, 'gscli -c "interface Ethernet1_1; mtu 3500; show"')
    assert "3500" in output

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu; show"')
    assert "mtu" not in output

    # check multiple 'no mtu' command won't crash
    ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu"')
    ssh(cli, 'gscli -c "interface Ethernet1_1; no mtu"')

    output = ssh(cli, 'gscli -c "show datastore /goldstone-interfaces:*"')
    assert "mtu" not in output
    assert "ipv4" not in output


def test_speed(cli):
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 100"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 100")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 1000000000000000000000000000"')
    except SSHException as e:
        assert "Invalid value" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid command: speed 1000000000000000000000000000"
        )
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 410000"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 410000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 400000"')
    except SSHException as e:
        assert "Invalid argument" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 400000")
    try:
        ssh(cli, 'gscli -c "interface Ethernet1_1; speed 25000"')
    except SSHException as e:
        assert "Invalid argument" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: speed 25000")

    # TODO this should fail
    # output = ssh(cli, 'gscli -c "interface Ethernet1_1; speed 25000; show"')

    output = ssh(cli, 'gscli -c "interface Ethernet1_1; speed 40000; show"')
    assert "40000" in output


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


def test_select_intf(cli):
    output = ssh(cli, 'gscli -c "interface .*; selected"')
    line = output.strip().split("\n")[-1]  # get the last line
    assert len(line.split(",")) == 20  # all interfaces should be selected

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


def test_mgmt_if_cmds(cli):
    try:
        ssh(cli, 'gscli -c "interface eth0; ip address 999.999.999.999/24"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd ip address 999.999.999.999/24"
        )
    try:
        ssh(cli, 'gscli -c "interface eth0; ip address 999.999.999.999.24"')
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
        'gscli -c "interface eth0; ip address 20.20.20.0/24; show running-config mgmt-if"',
    )
    assert "ip address 20.20.20.0/24" in output

    try:
        ssh(cli, 'gscli -c "interface eth0; no ip address 999.999.999.999/24"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception(
            "failed to fail with an invalid cmd no ip address 999.999.999.999/24"
        )
    try:
        ssh(cli, 'gscli -c "interface eth0; ip address 999.999.999.999.24"')
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
        'gscli -c "interface eth0; no ip address 20.20.20.0/24; show running-config mgmt-if"',
    )
    assert "ip address 20.20.20.0/24" not in output

    try:
        ssh(cli, 'gscli -c "interface eth0; ip route 10.10.10.117"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid cmd ip route 10.10.10.117")
    try:
        ssh(cli, 'gscli -c "interface eth0; ip route 10.10.10.117/35"')
    except SSHException as e:
        assert "does not satisfy the constraint" in e.stderr
    else:
        raise Exception("failed to fail with an invalid cmd ip route 10.10.10.117/35")
    output = ssh(
        cli,
        'gscli -c "interface eth0; ip route 30.30.30.0/24; show running-config mgmt-if"',
    )
    assert "ip route 30.30.30.0/24" in output

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.30.30.0/24" in output

    output = ssh(
        cli,
        'gscli -c "interface eth0; no ip route 30.30.30.0/24; show running-config mgmt-if"',
    )
    assert "ip route 30.30.30.0/24" not in output

    output = ssh(cli, 'gscli -c "show ip route"')
    assert "30.30.30.0/24" not in output

def test_onlp(cli):
    # ADD test for onlp CLIs here
    output = ssh(cli, 'gscli -c "show datastore /goldstone-onlp:* operational"')
    assert "piu" in output
    assert "sfp" in output
    print("Component PIU and SFP found in operational-DB")

def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        test_system(cli)

        test_vlan(cli)

        test_tai(cli)

        test_logging(cli)

        test_tacacs(host, cli)

        test_mtu(cli)

        test_speed(cli)

        test_invalid_intf(cli)

        test_select_intf(cli)

        test_statistics(cli)

        test_mgmt_intf(cli)

        test_mgmt_if_cmds(cli)

        try:
            test_vlan_member_add_delete(cli)
        except SSHException as e:
            print(f"test_vlan_member_add_delete() failed: {e}")
            ssh(cli, "kubectl get pods -A")
            ssh(cli, "kubectl logs -l app=gs-mgmt-sonic")
            ssh(cli, "kubectl describe pods -l app=gs-mgmt-sonic")
            sys.exit(1)

        try:
            test_port_breakout(cli)
        except SSHException as e:
            print(f"test_port_breakout() failed: {e}")
            ssh(cli, "kubectl get pods -A")
            ssh(cli, "kubectl logs -l app=gs-mgmt-sonic")
            ssh(cli, "kubectl describe pods -l app=gs-mgmt-sonic")
            sys.exit(1)

        test_onlp(cli)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone CI tool")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
