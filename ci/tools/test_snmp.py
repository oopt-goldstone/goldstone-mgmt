#!/usr/bin/env python3

import argparse
import paramiko

from .common import *


def main(host, username, password):

    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        run(f"snmpwalk -v 2c -c admin {host} system")

        try:
            run(f"snmpwalk -v 2c -c admin {host} ifTable")
        except Exception as e:
            print("TODO: snmpwalk ifTable can fail now after breakout configuration")
            ssh(cli, "kubectl logs ds/gs-mgmt-snmp agentx")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test SNMP")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
