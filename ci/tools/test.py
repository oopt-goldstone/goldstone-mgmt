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
        print("no transponder found on this device")
        return

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
    
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; output-power -1; show"')
    assert "-1" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no output-power; show"')
    assert "1" in output

    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; voa-rx 2; show"')
    assert "2" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no voa-rx; show"')
    assert "0" in output

    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; tx-laser-freq 193.7thz; show"')
    assert "193700000000000" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no tx-laser-freq; show"')
    assert "193500000000000" in output

    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; modulation-format dp-qpsk"')
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" ')
    assert "dp-qpsk" in output
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; no modulation-format"')
    output = ssh(cli, f'gscli -c "transponder {device}; netif 0; show" ')
    assert "dp-16-qam" in output

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

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" not in output

    for i in range(60):
        try:
            ssh(cli, 'gscli -c "show interface brief" | grep Ethernet5_2')
        except SSHException as e:
            time.sleep(1)
        else:
            print(f'uSONiC took {i}sec to restart')
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

    # Unconfigure
    ssh(cli, 'gscli -c "interface Ethernet5_1; no breakout"')

    # show interface brief should work during the usonic reboot
    output = ssh(cli, 'gscli -c "show interface brief"')
    assert "Ethernet5_1" in output
    assert "Ethernet5_2" in output

    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")
    for i in range(60):
        try:
            ssh(cli, 'gscli -c "show interface brief" | grep Ethernet5_2')
        except SSHException as e:
            print(f'uSONiC took {i}sec to restart')
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

def test_select_intf(cli):
    output = ssh(cli, 'gscli -c "interface .*; selected"')
    line = output.strip().split('\n')[-1] # get the last line
    assert len(line.split(',')) == 20 # all interfaces should be selected

def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        test_vlan(cli)

        test_tai(cli)

        test_logging(cli)

        test_mtu(cli)

        test_speed(cli)

        test_invalid_intf(cli)

        test_select_intf(cli)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone CI tool")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
