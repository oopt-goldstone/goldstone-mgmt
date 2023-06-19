# syntax=docker/dockerfile:1.4

ARG GS_MGMT_BUILDER_IMAGE
ARG GS_MGMT_BASE=python:3.10-slim-buster

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE as base

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            apt update && apt install -qy --no-install-recommends libatomic1 libpcre2-8-0 quilt

RUN pip install --upgrade pip

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i


RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/libyang/*.whl /usr/share/wheels/sysrepo/*.whl

RUN --mount=type=bind,source=sm/openroadm,target=/root/sm/openroadm,rw \
    --mount=type=bind,source=patches/openroadm,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    mkdir -p /var/lib/goldstone/yang/or && \
    cp -r /root/sm/openroadm/model/* /var/lib/goldstone/yang/or/

COPY yang /var/lib/goldstone/yang/gs/
ENV GS_YANG_REPO /var/lib/goldstone/yang/gs
COPY sm/openconfig/release/models/ /var/lib/goldstone/yang/oc/
ENV OC_YANG_REPO /var/lib/goldstone/yang/oc
COPY sm/openconfig/third_party/ietf/ /var/lib/goldstone/yang/ietf
ENV IETF_YANG_REPO /var/lib/goldstone/yang/ietf
ENV OR_YANG_REPO /var/lib/goldstone/yang/or

RUN --mount=type=bind,source=scripts,target=/src \
    cd /src && cp /src/gs-yang.py /usr/local/bin/

RUN pip install setuptools

RUN --mount=type=bind,source=src/lib,target=/src,rw pip install /src

RUN groupadd gsmgmt

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

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
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
# north-gnmi
#---

FROM builder AS gnmi-builder

RUN --mount=type=bind,source=.,target=/build,rw cd /build/src/north/gnmi \
    && make proto \
    && mkdir -p /tmp/build/goldstone/north/gnmi \
    && cp -r goldstone/north/gnmi/proto /tmp/build/goldstone/north/gnmi/

FROM base AS north-gnmi

COPY --from=gnmi-builder /tmp/build/goldstone/north/gnmi/proto /tmp/build/goldstone/north/gnmi/proto

RUN --mount=type=bind,source=src/north/gnmi,target=/src,rw cp -r /tmp/build/goldstone/north/gnmi/proto /src/goldstone/north/gnmi/ \
    && pip install /src

RUN rm -rf /tmp/build

RUN mkdir -p /current
RUN --mount=type=bind,source=scripts/,target=/scripts,rw cp /scripts/gnmi-supported-models.json /current

#---
# south-system
#---

FROM base AS south-system

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            apt update && apt install -qy --no-install-recommends libdbus-1-3

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/system/*.whl

RUN --mount=type=bind,source=src/south/system,target=/src,rw pip install /src

#---
# south-onlp
#---

FROM base AS south-onlp

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
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
# south-netlink
#---

FROM --platform=$BUILDPLATFORM rust:1-bullseye AS rust-builder

ARG TARGETPLATFORM
RUN case "$TARGETPLATFORM" in \
  "linux/arm64") echo aarch64-unknown-linux-gnu > /rust_target.txt; echo aarch64 > /arch.txt ;; \
  "linux/amd64") echo x86_64-unknown-linux-gnu > /rust_target.txt; echo x86_64 > /arch.txt ;; \
  *) exit 1 ;; \
esac

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends libclang1 clang apt-utils python3-pip

ARG TARGETARCH
RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            if [ $TARGETARCH=arm64 ]; then dpkg --add-architecture arm64; apt update && DEBIAN_FRONTEND=noninteractive apt install -qy g++-aarch64-linux-gnu libpcre2-dev:arm64 libatomic1:arm64; fi

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            if [ $TARGETARCH=amd64 ]; then apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends libpcre2-dev; fi

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | xargs dpkg -i --force-architecture
RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | xargs dpkg -i --force-architecture

RUN pip3 install cargo-zigbuild
COPY sm/sysrepo2-rs sm/sysrepo2-rs

WORKDIR /src/south/
RUN cargo new --bin netlink

WORKDIR /src/south/netlink

COPY src/south/netlink/Cargo.toml Cargo.toml

RUN rustup target add $(cat /rust_target.txt)

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/south/netlink/target \
    cargo zigbuild --release --target $(cat /rust_target.txt)

WORKDIR /

RUN rm -r src/south/netlink/src

COPY src/south/netlink/src src/south/netlink/src

WORKDIR /src/south/netlink

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/south/netlink/target \
    export CARGO_TARGET_$(cat /rust_target.txt | tr '[:lower:]-' '[:upper:]_')_RUSTFLAGS="-L /usr/lib/$(cat /arch.txt)-linux-gnu"; cargo zigbuild -r --target $(cat /rust_target.txt) && mv ./target/$(cat /rust_target.txt)/release/netlink /south-netlink

FROM debian:buster-slim AS south-netlink

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt,sharing=locked \
            apt update && apt install -qy --no-install-recommends libatomic1 libpcre2-8-0

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

COPY --from=rust-builder /south-netlink /usr/bin/

RUN groupadd gsmgmt

#---
# south-ocnos
#---

FROM base AS south-ocnos

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/ocnos/*.whl

RUN --mount=type=bind,source=src/south/ocnos,target=/src,rw pip install /src

#---
# xlate-oc (OpenConfig translator)
#---

FROM base AS xlate-oc

RUN --mount=type=bind,source=src/xlate/openconfig,target=/src,rw pip install /src

RUN mkdir -p /current
RUN --mount=type=bind,source=scripts/,target=/scripts,rw cp /scripts/operational-modes.json /current

#---
# xlate-or (OpenROADM translator)
#---

FROM base AS xlate-or

RUN --mount=type=bind,source=src/xlate/openroadm,target=/src,rw pip install /src

RUN mkdir -p /current
RUN --mount=type=bind,source=scripts/,target=/scripts,rw cp /scripts/operational-modes.json /current

#---
# system-telemetry
#---

FROM base AS system-telemetry

RUN --mount=type=bind,source=src/system/telemetry,target=/src,rw pip install /src

#---
# default image
#---

FROM base AS final

# vim:filetype=dockerfile
