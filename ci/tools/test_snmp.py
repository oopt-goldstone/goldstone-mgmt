#!/usr/bin/env python3

import argparse

from .common import *

def main(host, username, password):
    run(f"snmpwalk -v 2c -c admin {host}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test SNMP")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
