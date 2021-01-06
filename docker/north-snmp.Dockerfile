# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=docker.io/microsonic/gs-mgmt:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/root/sm/sonic-py-swsssdk,rw \
    --mount=type=bind,source=patches/sonic-py-swsssdk,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && cp -r /root/sm/sonic-py-swsssdk /

FROM $GS_MGMT_BASE

RUN --mount=type=bind,from=builder,source=/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/north/snmp,target=/src,rw pip install /src

# vim:filetype=dockerfile
