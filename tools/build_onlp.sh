#!/bin/bash

. setup.env
onlpm --rebuild-pkg-cache
onlpm --build onlp:amd64 onlp-dev:amd64 onlp-x86-64-kvm-x86-64-r0:amd64 onlp-py3:amd64
