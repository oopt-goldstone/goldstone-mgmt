# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=python:3-slim-buster

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && apt install -qy --no-install-recommends libatomic1

RUN pip install --upgrade pip

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i


RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/libyang/*.whl /usr/share/wheels/sysrepo/*.whl

COPY yang /var/lib/goldstone/yang/gs/
ENV GS_YANG_REPO /var/lib/goldstone/yang/gs
COPY sm/openconfig/release/models/ /var/lib/goldstone/yang/oc/
ENV OC_YANG_REPO /var/lib/goldstone/yang/oc
COPY sm/openconfig/third_party/ietf/ /var/lib/goldstone/yang/ietf
ENV IETF_YANG_REPO /var/lib/goldstone/yang/ietf

RUN --mount=type=bind,source=scripts,target=/src,rw \
    cd /src && cp /src/reload.sh /usr/local/bin/

RUN pip install setuptools

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src

# vim:filetype=dockerfile
