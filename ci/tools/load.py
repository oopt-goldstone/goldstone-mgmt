#!/usr/bin/env python3

import paramiko
import argparse
import sys
from scp import SCPClient
import time

from .common import *


def main(host, username, password, arch):

    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        ssh(
            cli, "kubectl delete -f /var/lib/rancher/k3s/server/manifests/mgmt || true"
        )  # can fail
        ssh(cli, "rm -rf /var/lib/rancher/k3s/server/manifests/mgmt")
        ssh(cli, "mkdir -p /var/lib/rancher/k3s/server/manifests/mgmt")

        if arch == "amd64":
            ssh(cli, "systemctl restart usonic")

        # stop South system service
        ssh(cli, "systemctl stop gs-south-system || true")  # can fail
        # stop Goldstone Management service
        ssh(cli, "systemctl stop gs-mgmt.target || true")  # can fail
        # stop NETOPEER2 service
        ssh(cli, "netopeer2.sh stop || true")  # can fail
        # stop SNMP service
        ssh(cli, "gs-snmp.sh stop || true")  # can fail

        images = [
            "gs-mgmt",
            "gs-mgmt-netopeer2",
            "gs-mgmt-snmpd",
            "gs-mgmt-south-onlp",
            "gs-mgmt-south-tai",
            "gs-mgmt-north-notif",
            "gs-mgmt-xlate-openconfig",
        ]

        if arch == "amd64":
            images.append("gs-mgmt-south-sonic")
            images.append("gs-mgmt-north-snmp")
        elif arch == "arm64":
            images.append("gs-mgmt-south-gearbox")

        images = " ".join(f"gs-test/{name}:latest-{arch}" for name in images)

        run(f"docker save -o /tmp/gs-mgmt-{arch}.tar {images}")

        # clean up sysrepo files
        ssh(cli, "rm -rf /dev/shm/sr_*")
        ssh(cli, "rm -rf /var/lib/sysrepo/*")

        scp = SCPClient(cli.get_transport())

        scp.put(f"/tmp/gs-mgmt-{arch}.tar", "/tmp")
        ssh(cli, f"ctr images import /tmp/gs-mgmt-{arch}.tar")

        scp.put(
            f"./ci/k8s/{arch}/prep.yaml",
            remote_path="/var/lib/rancher/k3s/server/manifests/mgmt/prep.yaml",
        )

        ssh(
            cli, "kubectl apply -f /var/lib/rancher/k3s/server/manifests/mgmt/prep.yaml"
        )

        ssh(cli, "kubectl wait --for=condition=complete job/prep-gs-mgmt --timeout 10m")

        scp.put(f"builds/{arch}/deb", recursive=True, remote_path="/tmp")
        ssh(cli, "dpkg -i /tmp/deb/*.deb")

        ssh(cli, "sysrepoctl -l | grep goldstone")  # goldstone models must be loaded

        apps = ["mgmt", "xlate"]
        if arch == "amd64":
            apps.append("south-sonic")
            apps.append("snmp")
        elif arch == "arm64":
            apps.append("south-gearbox")

        for app in apps:
            manifest = f"/var/lib/rancher/k3s/server/manifests/mgmt/{app}.yaml"
            scp.put(f"./ci/k8s/{arch}/{app}.yaml", manifest)
            ssh(cli, f"kubectl apply -f {manifest}")

        ssh(cli, "rm -rf /tmp/wheels")
        ssh(cli, "pip uninstall -y gscli gssystem libyang sysrepo")

        for v in ["libyang", "sysrepo", "cli", "system"]:
            ssh(cli, f"mkdir -p /tmp/wheels/{v}")
            path = f"builds/{arch}/wheels/{v}"
            scp.put(path, recursive=True, remote_path="/tmp/wheels")
            ssh(cli, f"pip install /tmp/wheels/{v}/*.whl")

        if arch == "amd64":
            check_pod(cli, "gs-mgmt-sonic")
            check_pod(cli, "gs-mgmt-snmp")
        elif arch == "arm64":
            check_pod(cli, "gs-mgmt-gearbox")

        check_pod(cli, "gs-mgmt-onlp")
        check_pod(cli, "gs-mgmt-tai")
        check_pod(cli, "gs-mgmt-openconfig")
        check_pod(cli, "gs-mgmt-notif")

        def restart_gssouth_system():
            max_iteration = 3
            for i in range(max_iteration):
                ssh(cli, "systemctl restart gs-south-system || true")
                time.sleep(1)
                output = ssh(cli, "systemctl status gs-south-system || true")
                if "Active: active (running)" in output:
                    print("Goldstone South System daemon is RUNNING")
                    break
                time.sleep(5)
            else:
                print("Goldstone South System daemon is NOT RUNNING")
                ssh(cli, "journalctl -u gssouth_system")
                sys.exit(1)

        restart_gssouth_system()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goldstone CI tool")
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")
    parser.add_argument("--arch", default="amd64", choices=["amd64", "arm64"])

    args = parser.parse_args()
    main(args.host, args.username, args.password, args.arch)
