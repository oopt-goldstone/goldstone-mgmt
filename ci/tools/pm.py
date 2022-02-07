#!/usr/bin/env python3

import paramiko
import argparse
import sys
from scp import SCPClient
import time

from .common import *


def main(host, username, password, arch, image_prefix, image_tag):

    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        models = ["goldstone-interfaces", "goldstone-transponder", "goldstone-platform"]

        for model in models:
            for _ in range(5):
                ssh(cli, f"sysrepocfg -X -m {model} -d operational", no_print=True)

        def check_pm(model, daemon):
            output = ssh(cli, f"kubectl logs --since=2m ds/{daemon}", no_print=True)
            for line in output.split("\n"):
                if f"/{model}:" in line and "elapsed" in line and "name" not in line:
                    print(line.strip())

        check_pm("goldstone-transponder", "south-tai")
        check_pm("goldstone-platform", "south-onlp")

        if arch == "arm64":
            daemon = "south-gearbox"
        elif arch == "amd64":
            daemon = "south-sonic"
        check_pm("goldstone-interfaces", daemon)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone CI tool")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")
    parser.add_argument("--arch", default="amd64", choices=["amd64", "arm64"])
    parser.add_argument(
        "--image-prefix", default="ghcr.io/oopt-goldstone/goldstone-mgmt"
    )
    parser.add_argument("--image-tag", default="")

    args = parser.parse_args()

    if args.image_tag == "":
        args.image_tag = f"latest-{args.arch}"
    main(
        args.host,
        args.username,
        args.password,
        args.arch,
        args.image_prefix,
        args.image_tag,
    )
