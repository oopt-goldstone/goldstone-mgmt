# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=gs-mgmt-builder:latest
ARG GS_MGMT_BASE=ubuntu:20.04

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && apt install -qy python3 vim curl python3-pip libgrpc++1

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN --mount=type=bind,source=sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64,target=/src dpkg -i /src/onlp_1.0.0_amd64.deb

COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/bin/sysrepocfg /usr/local/bin/sysrepocfg
COPY --from=builder /usr/local/bin/sysrepoctl /usr/local/bin/sysrepoctl
COPY --from=builder /usr/lib/python3 /usr/lib/python3
RUN ldconfig

ENV PYTHONPATH /usr/lib/python3/dist-packages

RUN --mount=type=bind,source=src/north/cli,target=/src,rw pip install /src

COPY src/south/tai/main /usr/bin/gssouthd-tai
COPY src/south/onlp/main /usr/bin/gssouthd-onlp

# vim:filetype=dockerfile
