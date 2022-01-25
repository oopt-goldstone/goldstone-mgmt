#!/usr/bin/env python3

import paramiko
import argparse

from .common import *


def run_np2_cli(host, user, password, command):
    return run(
        f"gscli --connector netconf --connector-opts host={host},username={user},password={password},hostkey_verify=false -c '{command}'"
    )


def test_get(host, user, password):
    run_np2_cli(host, user, password, "show interface brief")


def test_interface_admin_set(cli, host, user, password, ifname):
    ssh(cli, "gscli -c 'clear datastore all'")

    run_np2_cli(host, user, password, f"interface {ifname}; admin-status up")

    output = ssh(cli, "gscli -c 'show running-config'")
    assert "admin-status up" in output


def main(host, username, password, arch):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        ssh(cli, 'gscli -c "system; netconf; nacm; disable"')

        test_get(host, username, password)

        ifname = "Ethernet1_1" if arch == "amd64" else "'Interface1/1/1'"

        test_interface_admin_set(cli, host, username, password, ifname)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone test netconf server")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")
    parser.add_argument("--arch", default="amd64", choices=["amd64", "arm64"])

    args = parser.parse_args()
    main(args.host, args.username, args.password, args.arch)
