#!/bin/bash

. setup.env
onlpm --rebuild-pkg-cache
onlpm --build onlp:amd64 onlp-dev:amd64
