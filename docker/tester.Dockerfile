# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest

FROM $GS_MGMT_BUILDER_IMAGE AS builder

FROM python:3-buster

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends snmp software-properties-common make pkg-config curl git cmake libssh-4 libssh-dev libpcre3-dev quilt libclang1-6.0

RUN apt-add-repository non-free

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends snmp-mibs-downloader

RUN pip install paramiko scp black pyang prompt_toolkit tabulate natsort kubernetes setuptools

COPY scripts/snmp.conf /etc/snmp/snmp.conf

RUN rm /usr/share/snmp/mibs/ietf/SNMPv2-PDU

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,source=sm/libnetconf2,target=/root/sm/libnetconf2,rw cd /root && mkdir -p /build/libnetconf2 && cd /build/libnetconf2 && \
            cmake /root/sm/libnetconf2 && make && make install

RUN --mount=type=bind,source=sm/netopeer2,target=/root/sm/netopeer2,rw \
    --mount=type=bind,source=patches/np2,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /build/netopeer2 && cd /build/netopeer2 && \
    cmake /root/sm/netopeer2 && make && make install && mkdir -p /usr/local/share/netopeer2 && cp -r /root/sm/netopeer2/scripts /usr/local/share/netopeer2

RUN ldconfig

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/libyang/*.whl /usr/share/wheels/sysrepo/*.whl

COPY yang /var/lib/goldstone/yang/gs/
ENV GS_YANG_REPO /var/lib/goldstone/yang/gs
COPY sm/openconfig/release/models/ /var/lib/goldstone/yang/oc/
ENV OC_YANG_REPO /var/lib/goldstone/yang/oc
COPY sm/openconfig/third_party/ietf/ /var/lib/goldstone/yang/ietf
ENV IETF_YANG_REPO /var/lib/goldstone/yang/ietf

RUN --mount=type=bind,source=scripts,target=/src \
    cd /src && cp /src/gs-yang.py /usr/local/bin/

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src

COPY --from=docker:20.10 /usr/local/bin/docker /usr/local/bin/

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/south/sonic,target=/src,rw pip install -r /src/requirements.txt

RUN pip install grpcio-tools

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/tai/*.whl

RUN pip install GitPython # for tools/release.py

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src
RUN --mount=type=bind,source=src/north/cli,target=/src,rw pip install /src

RUN --mount=type=bind,source=sm/oopt-tai,target=/root/sm/oopt-tai,rw \
    cd /root/sm/oopt-tai/tools/meta-generator && pip install .

# vim:filetype=dockerfile
