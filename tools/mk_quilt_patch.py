#!/usr/bin/env python

import argparse
import subprocess
from git import Repo
import os
import sys
import gitdb

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submodule')
    parser.add_argument('--sha1')
    parser.add_argument('--list-submodules', '-l', action='store_true')

    args = parser.parse_args()

    repo = Repo(os.path.dirname(__file__) + '/..' )

    if args.list_submodules:
        print(' '.join(m.name for m in repo.submodules))
        return

    if args.submodule == None or args.sha1 == None:
        print('option --submodule and --sha1 is required')
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

    try:
        commit = sm.module().commit(args.sha1)
    except gitdb.exc.BadName as e:
        print(e)
        sys.exit(1)

    patch = commit.message.split('\n')[0].replace(' ', '_').replace('/', '_').lower() + '.patch'

    subprocess.run(['git', 'checkout', f'{args.sha1}^'], cwd=f'{os.path.dirname(__file__)}/../sm/{args.submodule}')
    subprocess.run(['quilt', 'new', args.submodule + '/' + patch])
    for filename in commit.stats.files.keys():
        subprocess.run(['quilt', 'add', f'{os.path.dirname(__file__)}/../sm/{args.submodule}/{filename}'])

    subprocess.run(['git', 'checkout', args.sha1], cwd=f'{os.path.dirname(__file__)}/../sm/{args.submodule}')
    subprocess.run(['quilt', 'refresh'])
    subprocess.run(['git', 'submodule', 'update', f'sm/{args.submodule}'], cwd=f'{os.path.dirname(__file__)}/../')

    if repo.is_dirty(path='sm/' + args.submodule):
        print("something went wrong")
        sys.exit(1)

    with open(f'{os.path.dirname(__file__)}/../patches/{args.submodule}/series') as f:
        series = f.read()

    if patch not in series:
        with open(f'{os.path.dirname(__file__)}/../patches/{args.submodule}/series', 'a') as f:
            f.write(patch + '\n')

if __name__ == '__main__':
    main()
