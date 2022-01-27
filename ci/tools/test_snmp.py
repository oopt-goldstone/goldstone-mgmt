#!/usr/bin/env python3

import argparse
import paramiko

from .common import *


def main(host, username, password, arch):

    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        run(f"snmpwalk -v 2c -c admin {host} system")
        version = run(f"snmpwalk -v 2c -c admin {host} SNMPv2-MIB::sysDescr.0")
        assert "unknown" not in version
        run(f"snmpwalk -v 2c -c admin {host} ifTable")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test SNMP")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")
    parser.add_argument("--arch", default="amd64", choices=["amd64", "arm64"])

    args = parser.parse_args()
    main(args.host, args.username, args.password, args.arch)
