# syntax=docker/dockerfile:1.4

ARG GS_MGMT_BUILDER_BASE=python:3-buster

FROM opennetworklinux/builder10:1.2 AS onlp
ARG TARGETARCH

SHELL ["/bin/bash", "-c"]
RUN --mount=type=bind,source=sm/OpenNetworkLinux,target=/root/sm/OpenNetworkLinux,rw \
    --mount=type=bind,source=.git/modules/sm/OpenNetworkLinux,target=/root/.git/modules/sm/OpenNetworkLinux,rw \
    cd /root/sm/OpenNetworkLinux && . ./setup.env && onlpm --rebuild-pkg-cache && mkdir -p /usr/share/onlp && \ 
    onlpm --build onlp:arm64 onlp-dev:arm64 onlp-py3:arm64 && \
    onlpm --build onlp:amd64 onlp-dev:amd64 onlp-py3:amd64 onlp-x86-64-kvm-x86-64-r0:amd64 && \
    cp -r REPO/buster/packages/binary-$TARGETARCH/* /usr/share/onlp && ls /usr/share/onlp

FROM $GS_MGMT_BUILDER_BASE AS base

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy gcc make pkg-config curl libclang1-6.0 doxygen libi2c-dev git cmake libpcre3-dev bison graphviz libcmocka-dev valgrind quilt libcurl4-gnutls-dev swig debhelper devscripts libpam-dev autoconf-archive libssl-dev dbus libffi-dev build-essential

RUN pip install --upgrade pip

FROM base AS sysrepo

RUN --mount=type=bind,source=sm/libyang,target=/root/sm/libyang,rw \
    --mount=type=bind,source=patches/libyang,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    mkdir -p /root/sm/libyang/build && cd /root/sm/libyang/build && \
    cmake .. && make build-deb && mkdir -p /usr/share/debs/libyang && cp debs/* /usr/share/debs/libyang/

RUN dpkg -i /usr/share/debs/libyang/*.deb

RUN --mount=type=bind,source=sm/sysrepo,target=/root/sm/sysrepo,rw \
    --mount=type=bind,source=patches/sysrepo,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /root/sm/sysrepo/build && cd /root/sm/sysrepo/build && \
    cmake -DREPO_PATH=/var/lib/sysrepo/ .. && make build-deb && mkdir -p /usr/share/debs/sysrepo && cp debs/* /usr/share/debs/sysrepo/ && \
    mkdir -p /usr/local/include/utils && cp /root/sm/sysrepo/src/utils/xpath.h /usr/local/include/utils/

RUN dpkg -i /usr/share/debs/sysrepo/*.deb

RUN pip install pyang clang jinja2 prompt_toolkit wheel

RUN mkdir -p /usr/share/wheels

RUN --mount=type=bind,source=sm/libyang-python,target=/root/sm/libyang-python,rw \
    --mount=type=bind,source=patches/libyang-python,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/libyang-python && python setup.py bdist_wheel \
    && mkdir -p /usr/share/wheels/libyang && cp dist/*.whl /usr/share/wheels/libyang

RUN --mount=type=bind,source=sm/sysrepo-python,target=/root/sm/sysrepo-python,rw \
    --mount=type=bind,source=patches/sysrepo-python,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/sysrepo-python && python setup.py bdist_wheel \
    && mkdir -p /usr/share/wheels/sysrepo && cp dist/*.whl /usr/share/wheels/sysrepo

FROM base AS pam
ARG TARGETARCH

RUN --mount=type=bind,source=sm/sonic-mgmt-common,target=/root/sm/sonic-mgmt-common,rw \
    --mount=type=bind,source=patches/sonic-mgmt,target=/root/patches \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /usr/local/sonic/ && cp -r /root/sm/sonic-mgmt-common/models/yang/sonic/* /usr/local/sonic/ && ls /usr/local/sonic/

RUN --mount=type=bind,source=sm/pam_tacplus,target=/root/sm/pam_tacplus,rw \
    --mount=type=bind,source=patches/pam,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/pam_tacplus && dpkg-buildpackage -rfakeroot -b -us -uc

RUN dpkg -i /root/sm/libtac2_1.4.1-1_${TARGETARCH}.deb
RUN dpkg -i /root/sm/libtac-dev_1.4.1-1_${TARGETARCH}.deb

RUN --mount=type=bind,source=sm/libnss-tacplus,target=/root/sm/libnss-tacplus,rw \
    --mount=type=bind,source=patches/nss,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/libnss-tacplus && dpkg-buildpackage -rfakeroot -b -us -uc && \
    cd /root/sm && mkdir -p /usr/share/debs/tacacs && cp *.deb /usr/share/debs/tacacs/

FROM sysrepo AS python

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy libdbus-glib-1-dev

RUN pip install grpcio-tools grpclib

RUN --mount=type=bind,source=src/lib,target=/src,rw \
    cd /src && python setup.py bdist_wheel \
    && mkdir -p /usr/share/wheels/lib && cp dist/*.whl /usr/share/wheels/lib

FROM python AS tai

RUN --mount=type=bind,source=sm/oopt-tai,target=/root/sm/oopt-tai,rw \
    cd /root/sm/oopt-tai/tools/taish && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/tai && cp dist/*.whl /usr/share/wheels/tai

FROM python AS cli

RUN --mount=type=bind,source=src/north/cli,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/cli && cp dist/*.whl /usr/share/wheels/cli

FROM python AS sonic

RUN pip install --upgrade pip
RUN pip install wheel grpcio-tools grpclib
RUN --mount=type=bind,source=src/south/sonic,target=/src,rw \
    cd /src && python -m grpc_tools.protoc -Iproto --python_out=. --python_grpc_out=. ./proto/goldstone/south/sonic/bcmd.proto \
    && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/sonic && cp dist/*.whl /usr/share/wheels/sonic

FROM python AS system

RUN --mount=type=bind,source=src/south/system,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/system && cp dist/*.whl /usr/share/wheels/system

FROM python AS builder

COPY --from=onlp /usr/share/onlp /usr/share/onlp
RUN dpkg -i /usr/share/onlp/*.deb

COPY --from=pam /usr/share/debs/tacacs /usr/share/debs/tacacs
COPY --from=pam /usr/local/sonic /usr/local/sonic

COPY --from=tai /usr/share/wheels/tai /usr/share/wheels/tai
RUN --mount=type=bind,source=sm/oopt-tai,target=/root/sm/oopt-tai,rw \
    cd /root/sm/oopt-tai/tools/meta-generator && pip install .

COPY --from=sysrepo /usr/share/debs/libyang /usr/share/debs/libyang
COPY --from=sysrepo /usr/share/wheels/libyang /usr/share/wheels/libyang

COPY --from=sysrepo /usr/share/debs/sysrepo /usr/share/debs/sysrepo
COPY --from=sysrepo /usr/share/wheels/sysrepo /usr/share/wheels/sysrepo

COPY --from=cli /usr/share/wheels/cli /usr/share/wheels/cli
COPY --from=sonic /usr/share/wheels/sonic /usr/share/wheels/sonic
COPY --from=system /usr/share/wheels/system /usr/share/wheels/system

RUN --mount=type=bind,source=scripts,target=/src \
    cd /src && cp /src/gs-yang.py /usr/local/bin/

#---
# tester
#---

FROM $GS_MGMT_BUILDER_BASE AS tester

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

#---
# host-packages
#---

FROM builder AS host-packages

RUN --mount=type=bind,source=src/lib,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && rm -rf /usr/share/wheels/lib && mkdir -p /usr/share/wheels/lib && cp dist/*.whl /usr/share/wheels/lib

RUN --mount=type=bind,source=src/north/cli,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && rm -rf /usr/share/wheels/cli && mkdir -p /usr/share/wheels/cli && cp dist/*.whl /usr/share/wheels/cli

RUN --mount=type=bind,source=src/south/system,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && rm -rf /usr/share/wheels/system && mkdir -p /usr/share/wheels/system && cp dist/*.whl /usr/share/wheels/system

#---
# default image
#---

FROM builder AS final

# vim:filetype=dockerfile
