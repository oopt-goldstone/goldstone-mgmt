import subprocess
import os
import sys


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
