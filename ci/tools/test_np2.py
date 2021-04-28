#!/usr/bin/env python3

import paramiko
import argparse
import time
import sys
from scp import SCPClient
import tempfile

from .common import *

def run_np2_cli(cli, host, commands):
    run("rm -rf id_rsa id_rsa.pub")
    run("ssh-keygen -f id_rsa -N ''")
    ssh(cli, "mkdir -p /home/admin/.ssh")
    scp = SCPClient(cli.get_transport())
    scp.put("id_rsa.pub", "/home/admin/.ssh/authorized_keys")
    ssh(cli, "chown admin:admin /home/admin/.ssh/authorized_keys")

    cmd = "\n".join(commands)

    with open("/tmp/check_np2.sh", "w") as f:
        f.write(
            f"""#!/bin/sh
netopeer2-cli <<EOF
auth pref publickey 4
auth keys add id_rsa.pub id_rsa
auth hostkey-check disable
connect --host {host} --login admin
{cmd}
EOF
"""
        )
    run("chmod +x /tmp/check_np2.sh && /tmp/check_np2.sh")

def test_get(cli, host):
    run_np2_cli(cli, host, ["status", "get --filter-xpath '/goldstone-interfaces:*'", "get-config --source running --filter-xpath '/goldstone-tai:modules'"])


def test_interface_admin_set(cli, host):
    ssh(cli, "gscli -c 'clear datastore all'")

    config = "config.xml"
    with open(config, "w") as f:
        f.write("""<interfaces xmlns="http://goldstone.net/yang/goldstone-interfaces">
  <interface>
    <name>Ethernet1_1</name>
    <admin-status>down</admin-status>
  </interface>
</interfaces>""")

    run_np2_cli(cli, host, [f"edit-config --target running --config={config}", "commit"])
    output = ssh(cli, "gscli -c 'show running-config'")
    assert "shutdown" in output


def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        ssh(cli, 'gscli -c "system; netconf; nacm; disable"')

        test_get(cli, host)

        test_interface_admin_set(cli, host)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test netconf server")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
