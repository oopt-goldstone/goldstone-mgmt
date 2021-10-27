# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-builder:latest
ARG GS_MGMT_NP2_IMAGE=docker.io/microsonic/gs-mgmt-netopeer2:latest

FROM $GS_MGMT_BUILDER_IMAGE AS builder

FROM $GS_MGMT_NP2_IMAGE

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends python3 python3-pip python3-setuptools snmp software-properties-common

RUN apt-add-repository non-free

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends snmp-mibs-downloader

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN pip install --upgrade pip

RUN pip install paramiko scp black pyang prompt_toolkit tabulate natsort kubernetes setuptools

COPY ci/docker/snmp.conf /etc/snmp/snmp.conf

RUN rm /usr/share/snmp/mibs/ietf/SNMPv2-PDU

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

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src

COPY --from=docker:19.03 /usr/local/bin/docker /usr/local/bin/

# vim:filetype=dockerfile
