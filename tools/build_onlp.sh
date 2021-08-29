#!/bin/bash

. setup.env
onlpm --rebuild-pkg-cache

if [ $1 = amd64 ]; then
    onlpm --build onlp:amd64 onlp-dev:amd64 onlp-x86-64-kvm-x86-64-r0:amd64 onlp-py3:amd64
elif [ $1 = arm64 ]; then
    onlpm --build onlp:arm64 onlp-dev:arm64 onlp-arm64-wistron-wtp-01-c1-00-r0:arm64 onlp-py3:arm64
fi
