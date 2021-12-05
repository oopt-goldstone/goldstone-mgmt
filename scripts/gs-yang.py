#!/usr/bin/env python

import argparse
import subprocess
from pathlib import Path
import os
import fcntl
import itertools
import sys

MODELS = {
    "south-onlp": ["goldstone-platform", "goldstone-component-connection"],
    "south-sonic": [
        "goldstone-interfaces",
        "goldstone-vlan",
        "goldstone-uplink-failure-detection",
        "goldstone-ip",
        "goldstone-portchannel",
        "goldstone-component-connection",
    ],
    "south-tai": ["goldstone-transponder", "goldstone-component-connection"],
    "south-gearbox": [
        "goldstone-interfaces",
        "goldstone-gearbox",
        "goldstone-component-connection",
    ],
    "south-system": [
        "goldstone-aaa",
        "goldstone-mgmt-interfaces",
        "goldstone-ip",
        "goldstone-system",
        "goldstone-routing",
    ],
    "xlate-oc": [
        "iana-if-type",
        "interfaces/openconfig-interfaces",
        "platform/openconfig-platform-types",
        "platform/openconfig-platform-port",
        "platform/openconfig-platform",
    ],
}

DEFAULT_YANG_DIR = "/var/lib/goldstone/yang"
DEFAULT_PLATFORM_YANG_DIR = "/var/lib/goldstone/device/current/yang"


def install_model(model_name: str, search_dirs: list[str] = []) -> None:
    with open("/run/gs-yang-lock", "wt") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)

            s = "--search-dirs " + ":".join(search_dirs)

            model = list(
                itertools.chain.from_iterable(
                    [Path(d).rglob(f"{model_name}.yang") for d in search_dirs]
                )
            )
            if len(model) == 0:
                raise Exception(f"model {model_name} not found")
            elif len(model) > 1:
                raise Exception(f"multiple models named {model_name} found")

            model = model[0]

            print(model, search_dirs)

            command = f"sysrepoctl {s} --install {model}"
            print(f"run: {command}")
            subprocess.run(command.split(" "), stderr=subprocess.STDOUT)
            name, _ = os.path.splitext(os.path.basename(model))
            command = f"sysrepoctl -c {name} -g gsmgmt -p 664"
            print(f"run: {command}")
            subprocess.run(command.split(" "), stderr=subprocess.STDOUT)

        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def install_platform(yang_dir):
    if yang_dir == None:
        yang_dir = DEFAULT_PLATFORM_YANG_DIR
    path = Path(yang_dir)
    for m in path.glob("*.yang"):
        install_model(m, [yang_dir])


def install(name, yang_dir):
    if yang_dir == None:
        yang_dir = [DEFAULT_YANG_DIR]
    for model in MODELS[name]:
        install_model(model, yang_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", nargs="+")
    parser.add_argument("--install-platform", action="store_true")
    parser.add_argument("--search-dirs", nargs="+")

    args = parser.parse_args()

    if args.install_platform:
        install_platform(args.search_dirs)

    if args.install:

        daemons = args.install

        choices = MODELS.keys()

        if not all(d in choices for d in daemons):
            print(f"choose from {', '.join(list(choices))}")
            sys.exit(1)

        for d in daemons:
            install(d, args.search_dirs)


if __name__ == "__main__":
    main()
