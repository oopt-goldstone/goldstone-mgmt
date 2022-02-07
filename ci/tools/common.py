import subprocess
import os
import sys
import time


class ProcException(Exception):
    def __init__(self, msg, ret, stdout, stderr):
        super().__init__(msg)
        self.ret = ret
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return "".join(self.stderr)


class SSHException(ProcException):
    pass


def ssh(cli, cmd, no_print=False):
    if not no_print:
        print(f'ssh: "{cmd}"')
    _, stdout, stderr = cli.exec_command(cmd)
    output = []
    err = []
    for line in stdout:
        output.append(line)
        if not no_print:
            print(f"stdout: {line}", end="")
    for line in stderr:
        err.append(line)
        if not no_print:
            print(f"stderr: {line}", end="")
    ret = stdout.channel.recv_exit_status()
    if ret != 0:
        raise SSHException(
            f"{cmd} failed: ret: {ret}", ret, "".join(output), "".join(err)
        )

    return "".join(output)


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
        raise ProcException(
            f"{cmd} failed: ret: {ret}", ret, "".join(output), "".join(err)
        )

    return "".join(output)


def check_pod(cli, name, max_iteration=48, sleep=10):
    for i in range(max_iteration):
        time.sleep(sleep)

        try:
            condition = ssh(
                cli,
                f"kubectl get pod -l app={name} -o jsonpath='{{.items[0].status.conditions}}' | jq -r '.[] | select ( .type | test(\"^Ready$\")) | .status'",
            )
            status = ssh(
                cli,
                f"kubectl get pod -l app={name} -o jsonpath='{{.items[0].status.phase}}'",
            )
        except SSHException:
            continue

        if condition.strip() == "True" and status.strip() == "Running":
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
