# syntax=docker/dockerfile:1.4

ARG GS_MGMT_BUILDER_IMAGE
ARG GS_MGMT_BASE=python:3-slim-buster

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE as base

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && apt install -qy --no-install-recommends libatomic1 libpcre2-8-0

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

RUN --mount=type=bind,source=scripts,target=/src \
    cd /src && cp /src/gs-yang.py /usr/local/bin/

RUN pip install setuptools

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src

#---
# north-cli
#---

FROM base AS north-cli

RUN --mount=type=bind,source=src/north/cli,target=/src,rw pip install /src

#---
# north-notification
#---

FROM base AS north-notif

RUN --mount=type=bind,source=src/north/notif,target=/src,rw pip install /src

#---
# north-netconf
#---

FROM debian:10 AS north-netconf

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy make pkg-config curl git cmake libssh-4 libssh-dev libpcre2-dev quilt

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,source=sm/libnetconf2,target=/root/sm/libnetconf2,rw cd /root && mkdir -p /build/libnetconf2 && cd /build/libnetconf2 && \
            cmake /root/sm/libnetconf2 && make && make install

RUN --mount=type=bind,source=sm/netopeer2,target=/root/sm/netopeer2,rw \
    --mount=type=bind,source=patches/netopeer2,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /build/netopeer2 && cd /build/netopeer2 && \
    cmake /root/sm/netopeer2 && make && make install && mkdir -p /usr/local/share/netopeer2 && cp -r /root/sm/netopeer2/scripts /usr/local/share/netopeer2

RUN ldconfig

#---
# north-snmp (agentx)
#---

FROM builder AS snmp-builder

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/root/sm/sonic-py-swsssdk,rw \
    --mount=type=bind,source=patches/sonic-py-swsssdk,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && cp -r /root/sm/sonic-py-swsssdk /

FROM base AS north-snmp

RUN --mount=type=bind,from=snmp-builder,source=/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/north/snmp,target=/src,rw pip install /src

#---
# south-system
#---

FROM base AS south-system

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && apt install -qy --no-install-recommends libdbus-1-3

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/system/*.whl

RUN --mount=type=bind,source=src/south/system,target=/src,rw pip install /src

#---
# south-onlp
#---

FROM base AS south-onlp

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && apt install -qy --no-install-recommends libi2c0

RUN --mount=type=bind,from=builder,source=/usr/share/onlp,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN ldconfig

RUN --mount=type=bind,source=src/south/onlp,target=/src,rw pip install /src

#---
# south-tai
#---

FROM base AS south-tai

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/tai/*.whl

RUN --mount=type=bind,source=src/south/tai,target=/src,rw pip install /src

#---
# south-sonic
#---

FROM builder AS sonic-builder

RUN pip install --upgrade pip
RUN pip install wheel grpcio-tools grpclib
RUN --mount=type=bind,source=src/south/sonic,target=/src,rw \
    cd /src && python -m grpc_tools.protoc -Iproto --python_out=. --python_grpc_out=. ./proto/goldstone/south/sonic/bcmd.proto \
    && python setup.py bdist_wheel \
    && mkdir -p /usr/share/wheels/sonic && cp dist/*.whl /usr/share/wheels/sonic

FROM base AS south-sonic

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,from=builder,source=/usr/share/wheels/sonic,target=/sonic pip install /sonic/*.whl

#---
# south-gearbox
#---

FROM base AS south-gearbox

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/tai/*.whl

RUN --mount=type=bind,source=src/south/gearbox,target=/src,rw pip install /src

#---
# south-dpll
#---

FROM base AS south-dpll

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/tai/*.whl

RUN --mount=type=bind,source=src/south/dpll,target=/src,rw pip install /src

#---
# xlate-oc (OpenConfig translator)
#---

FROM base AS xlate-oc

RUN --mount=type=bind,source=src/xlate/openconfig,target=/src,rw pip install /src

#---
# default image
#---

FROM base AS final

# vim:filetype=dockerfile
