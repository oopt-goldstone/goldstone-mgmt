#!/usr/bin/env python3

from subprocess import run
import argparse
import paramiko
import os

# config = paramiko.config.SSHConfig.from_path(os.environ["HOME"] + "/.ssh/config")
#
# for host in ["g3", "gft1"]:
#    hostconfig = config.lookup(host)


def main(host, username, password):

    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username, password)

        for model in ["interfaces", "transponder", "platform"]:
            _, stdout, _ = ssh.exec_command(
                f"sysrepocfg -X -m goldstone-{model} -d operational"
            )

            output = "".join(line for line in stdout)
            with open(f"goldstone-{model}-operational.xml", "w") as f:
                f.write(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--username", default="root")
    parser.add_argument("--password", default="x1")

    args = parser.parse_args()
    main(args.host, args.username, args.password)
