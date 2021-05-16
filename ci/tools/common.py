import subprocess
import os
import sys
import time


class SSHException(Exception):
    def __init__(self, msg, ret, stdout, stderr):
        super().__init__(msg)
        self.ret = ret
        self.stdout = stdout
        self.stderr = stderr


def ssh(cli, cmd):
    print(f'ssh: "{cmd}"')
    _, stdout, stderr = cli.exec_command(cmd)
    output = []
    err = []
    for line in stdout:
        output.append(line)
        print(f"stdout: {line}", end="")
    for line in stderr:
        err.append(line)
        print(f"stderr: {line}", end="")
    ret = stdout.channel.recv_exit_status()
    if ret != 0:
        raise SSHException(
            f"{cmd} failed: ret: {ret}", ret, "".join(output), "".join(err)
        )

    return "".join(output)


def run(cmd):
    print(f'run: "{cmd}"')
    subprocess.run(
        cmd,
        shell=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
        env=os.environ,
    )

def check_pod(cli, name, max_iteration=48, sleep=5):
    for i in range(max_iteration):
        time.sleep(sleep)
        status = ssh(
            cli,
            f"kubectl get pod -l app={name} -o jsonpath='{{.items[0].status.conditions}}' | jq -r '.[] | select ( .type | test(\"^Ready$\")) | .status'",
        )
        if status.strip() == "True":
            return
        print(
            f"{name} not running yet. status = {status}. waiting.. {i}/{max_iteration}"
        )
    else:
        print("timeout")
        ssh(cli, "kubectl get pods -A")
        ssh(cli, f"kubectl describe pods -l app={name}")
        ssh(cli, f"kubectl logs ds/{name}")
        sys.exit(1)
