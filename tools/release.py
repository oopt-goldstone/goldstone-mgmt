#!/usr/bin/env python

import subprocess
from git import Repo
import os
import sys


def main():
    root = os.path.relpath(os.path.dirname(__file__) + "/..")
    repo = Repo(root)

    if repo.is_dirty():
        print("can't work with a dirty repo")
        sys.exit(1)

    cmd = ("git", "describe", "--tags", "--always")
    version = subprocess.check_output(cmd).strip().decode()

    for arch in ["amd64", "arm64"]:
        env = {
            "GS_MGMT_IMAGE_TAG": f"{version}-{arch}",
            "ARCH": arch,
        }
        cmd = ("make", "-C", root, "builder")
        subprocess.run(cmd, env=env)

        cmd = ("make", "-C", root, "base-image")
        subprocess.run(cmd, env=env)

        env["GS_SAVE_AFTER_BUILD"] = "1"

        cmd = ("make", "-C", root, "images", "host-packages")
        subprocess.run(cmd, env=env)


if __name__ == "__main__":
    main()
