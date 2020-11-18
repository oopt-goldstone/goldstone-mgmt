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
    subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr, check=True, env=os.environ)


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
    lines = [ line for line in output.split() if '/dev' in line ]

    if len(lines) == 0:
        print("no transponder found on this device")
        return

    elems = [ elem for elem in lines[0].split('|') if '/dev' in elem ]
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
    try :
        ssh(cli, 'gscli -c "interface Ethernet5_1; breakout 4X10GB"')
    except:
        print("This was 'Negative Testcase' for Breakout configuration")

    ssh(cli, 'gscli -c "interface Ethernet5_1; breakout 4X10G"')
    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")
    time.sleep(60)
    #Validating if 'syncd' has come up properly
    validate_str = 'sending switch_shutdown_request notification to OA'
    output = ssh(cli, 'kubectl logs deploy/usonic syncd')
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
    # Wait for usonic to come up
    print("Waiting asychronosly for 'usonic' to come up ")
    time.sleep(60)
    #Validating if 'syncd' has come up properly
    output = ssh(cli, 'kubectl logs deploy/usonic syncd')
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
    time.sleep(5)
    ssh(cli, 'gscli -c "show logging 50"')
    time.sleep(5)
    ssh(cli, 'gscli -c "show logging sonic 50"')
    time.sleep(5)
    ssh(cli, 'gscli -c "show logging sonic"')
    time.sleep(5)
    ssh(cli, 'gscli -c "show logging onlp 100"')
    time.sleep(5)
    try:
        ssh(cli, 'gscli -c "show logging h01"')
    except SSHException as e:
        assert "show logging [sonic|tai|onlp|] [<num_lines>|]" in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: show logging h01")


def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        test_vlan(cli)

        test_tai(cli)

        test_logging(cli)

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
