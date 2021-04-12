#!/usr/bin/env python

import argparse
import subprocess
from git import Repo
import os
import sys
import gitdb
import time

def run(args, cwd=None):
    print(f'cmd: {args}, cwd: {cwd}')
    subprocess.run(args, cwd=cwd)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submodule')
    parser.add_argument('--sha1')
    parser.add_argument('--list-submodules', '-l', action='store_true')
    parser.add_argument('--stage', '-s', action='store_true', help='stage a temporal branch which applies all patches for the specified submodule')

    args = parser.parse_args()

    root = os.path.relpath(os.path.dirname(__file__) + '/..')
    repo = Repo(root)

    if args.list_submodules:
        print('\n'.join(m.name.split('/')[-1] for m in repo.submodules))
        return

    if args.submodule == None:
        print('option --submodule is required')
        sys.exit(1)

    if 'sm/' + args.submodule not in [m.name for m in repo.submodules]:
        print(f'submodule {args.submodule} not found')
        sys.exit(1)

    if repo.is_dirty(path='sm/' + args.submodule):
        print("can't work with a dirty submodule")
        sys.exit(1)

    sm = None
    for m in repo.submodules:
        if 'sm/' + args.submodule == m.name:
            sm = m
            break

    if args.stage:
        d = f'{root}/patches'
        run(['rm', '-rf', f'{root}/.pc'])
        run(['sudo', 'mount', '--bind', f'{d}/{args.submodule}', d])
        try:
            run(['quilt', 'push', '-a'])
        finally:
            run(['sudo', 'umount', d])
        return

    if args.sha1 == None:
        print('option --sha1 is required')
        sys.exit(1)

    try:
        commit = sm.module().commit(args.sha1)
    except gitdb.exc.BadName as e:
        print(e)
        sys.exit(1)

    patch = commit.message.split('\n')[0].replace(' ', '_').replace('/', '_').lower() + '.patch'

    run(['git', 'checkout', f'{args.sha1}^'], cwd=f'{root}/sm/{args.submodule}')
    run(['quilt', 'new', args.submodule + '/' + patch], cwd=root)
    for filename in commit.stats.files.keys():
        run(['quilt', 'add', f'{root}/sm/{args.submodule}/{filename}'], cwd=root)

    run(['git', 'checkout', args.sha1], cwd=f'{root}/sm/{args.submodule}')
    run(['quilt', 'refresh'], cwd=root)
    run(['git', 'submodule', 'update', f'sm/{args.submodule}'], cwd=root)

    if repo.is_dirty(path='sm/' + args.submodule):
        print("something went wrong")
        sys.exit(1)

    d = f'{root}/patches/{args.submodule}'
    os.makedirs(d, exist_ok=True)

    try:
        with open(f'{d}/series') as f:
            series = f.read()
    except:
        series = ""

    if patch not in series:
        with open(f'{d}/series', 'a') as f:
            f.write(patch + '\n')

if __name__ == '__main__':
    main()
