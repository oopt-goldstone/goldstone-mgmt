#!/usr/bin/env python3

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
        "goldstone-sonic",
        "goldstone-vlan",
        "goldstone-uplink-failure-detection",
        "goldstone-portchannel",
        "goldstone-component-connection",
    ],
    "south-tai": ["goldstone-transponder", "goldstone-component-connection"],
    "south-gearbox": [
        "goldstone-interfaces",
        "goldstone-gearbox",
        "goldstone-component-connection",
        "goldstone-static-macsec",
        "goldstone-synce",
        "goldstone-dpll",
    ],
    "south-netlink": [
        "goldstone-interfaces",
        "goldstone-mgmt-interfaces",
        "goldstone-ipv4",
    ],
    "south-dpll": ["goldstone-dpll"],
    "south-system": [
        "goldstone-aaa",
        "goldstone-system",
    ],
    "xlate-oc": [
        "iana-if-type",
        "types/openconfig-types",
        "types/openconfig-yang-types",
        "interfaces/openconfig-interfaces",
        "interfaces/openconfig-if-ethernet",
        "platform/openconfig-platform",
        "platform/openconfig-platform-types",
        "platform/openconfig-platform-port",
        "platform/openconfig-platform-transceiver",
        "platform/openconfig-platform-fan",
        "platform/openconfig-platform-psu",
        "optical-transport/openconfig-terminal-device",
        "optical-transport/openconfig-transport-line-common",
        "optical-transport/openconfig-transport-types",
        "telemetry/openconfig-telemetry",
        "telemetry/openconfig-telemetry-types",
    ],
    "xlate-or": [
        "Device/org-openroadm-device",
        "Device/org-openroadm-ethernet-interfaces",
        "Device/org-openroadm-optical-tributary-signal-interfaces",
        "Device/org-openroadm-otn-odu-interfaces",
        "Device/org-openroadm-otn-otu-interfaces",
        "Device/org-openroadm-otsi-group-interfaces",
        "Common/org-openroadm-common-optical-channel-types",
        "Common/org-openroadm-common-types",
        "Common/org-openroadm-otn-common-types",
        "Common/org-openroadm-pm",
        "Common/org-openroadm-pm-types",
        "Common/org-openroadm-interfaces",
    ],
    "system-telemetry": [
        "goldstone-telemetry",
    ],
    "south-ocnos": [
        "iana-if-type",
        "goldstone-interfaces",
        "goldstone-uplink-failure-detection",
        "goldstone-vlan",
        "goldstone-portchannel",
    ],
}

DEFAULT_YANG_DIR = "/var/lib/goldstone/yang"
DEFAULT_PLATFORM_YANG_DIR = "/var/lib/goldstone/device/current/yang"


def run(cmd):
    print(f'run: "{cmd}"')
    proc = subprocess.run(
        cmd,
        shell=True,
        env=os.environ,
        capture_output=True,
    )
    output = []
    err = []
    for line in proc.stdout.decode().split("\n"):
        output.append(line)
        print(f"stdout: {line}")
    for line in proc.stderr.decode().split("\n"):
        err.append(line)
        print(f"stderr: {line}")
    ret = proc.returncode
    if ret != 0:
        raise Exception(f"{cmd} failed: ret: {ret}", ret, "".join(output), "".join(err))

    return "".join(output)


def install_model(model_name: str, search_dirs=[]) -> None:
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

            run(f"sysrepoctl {s} --install {model}")
            name, _ = os.path.splitext(os.path.basename(model))
            run(f"sysrepoctl -c {name} -g gsmgmt -p 664")

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


def lint(daemons, search_dirs=[]):
    if not search_dirs:
        search_dirs = [DEFAULT_YANG_DIR, "/usr/local/share/yang/modules/ietf"]

    models = []
    for model_name in set(itertools.chain.from_iterable(MODELS[d] for d in daemons)):

        model = list(
            itertools.chain.from_iterable(
                [Path(d).rglob(f"{model_name}.yang") for d in search_dirs]
            )
        )

        if len(model) == 0:
            raise Exception(f"model {model_name} not found")
        elif len(model) > 1:
            raise Exception(f"multiple models named {model_name} found")

        models.append(str(model[0]))

    path = "--path=" + ":".join(search_dirs)
    run(f"pyang {path} {' '.join(models)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", nargs="+")
    parser.add_argument("--install-platform", action="store_true")
    parser.add_argument("--search-dirs", nargs="+")
    parser.add_argument("--lint", nargs="+")
    parser.add_argument("--fix-perm", action="store_true")

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

    if args.lint:
        daemons = args.lint

        choices = MODELS.keys()

        if not all(d in choices for d in daemons):
            print(f"choose from {', '.join(list(choices))}")
            sys.exit(1)

        lint(daemons, args.search_dirs)

    if args.fix_perm:
        run("sysrepoctl -c ':ALL' -g gsmgmt -p 664")
        run("chmod g+w /dev/shm/sr_main")
        run("chgrp gsmgmt /dev/shm/sr_main")


if __name__ == "__main__":
    main()
