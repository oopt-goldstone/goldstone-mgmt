#!/usr/bin/env python3

import paramiko
import argparse
import subprocess
import sys
from scp import SCPClient
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
        print(f'stdout: {line}', end='')
    for line in stderr:
        err.append(line)
        print(f'stderr: {line}', end='')
    ret = stdout.channel.recv_exit_status()
    if ret != 0:
        raise SSHException(f'{cmd} failed: ret: {ret}', ret, ''.join(output), ''.join(err))

    return ''.join(output)

def run(cmd):
    print(f'run: "{cmd}"')
    subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr, check=True)

def test_vlan(cli):
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "vlan 2000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 2000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "no vlan 1000"')
    ssh(cli, 'gscli -c "show vlan details"')
    ssh(cli, 'gscli -c "show interface brief"')
    ssh(cli, 'gscli -c "show interface description"')
    ssh(cli, 'gscli -c "show tech-support"')
    ssh(cli, 'gscli -c "show running-config"')
    ssh(cli, 'gscli -c "show running-config interface"')
    ssh(cli, 'gscli -c "show running-config vlan"')

def test_tai(cli):
    ssh(cli, 'gscli -c "transponder /dev/piu4; netif 0; show"')
    ssh(cli, 'gscli -c "transponder /dev/piu4; netif 0; tx-laser-freq 194.5thz"')
    ssh(cli, 'gscli -c "transponder /dev/piu4; netif 0; show"')

    try:
        ssh(cli, 'gscli -c "transponder /dev/piu4; netif 0; tx-laser-freq aaa"')
    except SSHException as e:
        assert 'invalid frequency input' in e.stderr
    else:
        raise Exception("failed to fail with an invalid command: tx-laser-freq aaa")

def main(host, username, password):
    with paramiko.SSHClient() as cli:
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(host, username=username, password=password)

        ssh(cli, 'kubectl delete -f /var/lib/rancher/k3s/server/manifests/mgmt || true') # can fail
        ssh(cli, 'rm -rf /var/lib/rancher/k3s/server/manifests/mgmt')

        ssh(cli, 'systemctl restart usonic')

        run('docker save -o /tmp/gs-mgmt.tar gs-test/gs-mgmt-debug:latest')

        scp = SCPClient(cli.get_transport())
        scp.put('/tmp/gs-mgmt.tar', '/tmp')
        ssh(cli, 'ctr images import /tmp/gs-mgmt.tar')

        scp.put('./ci/k8s', recursive=True, remote_path='/var/lib/rancher/k3s/server/manifests/mgmt')

        run('make docker')
        scp.put('./src/north/cli/dist/gscli-0.1.0-py3-none-any.whl', remote_path='/tmp/')
        ssh(cli, 'pip3 uninstall -y gscli')
        ssh(cli, 'pip3 install /tmp/*.whl')

        #ssh(cli, 'gscli -c "show version"')

        ssh(cli, 'rm -rf /dev/shm/sr_*')
        ssh(cli, 'rm -rf /var/lib/sysrepo/*')
        ssh(cli, 'kubectl apply -f /var/lib/rancher/k3s/server/manifests/mgmt')

        def check_pod(name):
            max_iteration = 4
            for i in range(max_iteration):
                time.sleep(5)
                status = ssh(cli, f"kubectl get pod -l app={name} -o jsonpath='{{.items[0].status.phase}}'")
                if status == 'Running':
                    return
                print(f'{name} not running yet. status = {status}. waiting.. {i}/{max_iteration}')
            else:
                print('timeout')
                ssh(cli, "kubectl get pods -A")
                ssh(cli, f"kubectl describe pods -l app={name}")
                sys.exit(1)

        check_pod('gs-mgmt-onlp')
        check_pod('gs-mgmt-sonic')
        check_pod('gs-mgmt-tai')

        test_vlan(cli)

        test_tai(cli)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Goldstone CI tool')
    parser.add_argument('host')
    parser.add_argument('--username', default='root')
    parser.add_argument('--password', default='x1')

    args = parser.parse_args()
    main(args.host, args.username, args.password)

