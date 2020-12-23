#!/usr/bin/env python3

import paramiko
import argparse
import time
import sys
from scp import SCPClient
import tempfile

from .common import *

def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        ssh(cli, 'gscli -c "system; netconf; nacm; disable"')

        run("rm -rf id_rsa id_rsa.pub")
        run("ssh-keygen -f id_rsa -N ''")
        ssh(cli, "mkdir -p /home/admin/.ssh")
        scp = SCPClient(cli.get_transport())
        scp.put("id_rsa.pub", "/home/admin/.ssh/authorized_keys")
        ssh(cli, "chown admin:admin /home/admin/.ssh/authorized_keys")

        with open("/tmp/check_np2.sh", "w") as f:
            f.write(f"""#!/bin/sh

netopeer2-cli <<EOF
auth pref publickey 4
auth keys add id_rsa.pub id_rsa
auth hostkey-check disable
connect --host {host} --login admin
status
get --filter-xpath "/goldstone-interfaces:*"
get-config --source running --filter-xpath "/goldstone-tai:modules"

EOF
""")
        run("chmod +x /tmp/check_np2.sh && /tmp/check_np2.sh")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test netconf server")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
