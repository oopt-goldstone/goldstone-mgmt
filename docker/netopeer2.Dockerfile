# syntax=docker/dockerfile:experimental

# ubuntu:20.04's libssh won't work

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-builder:latest
ARG GS_NETOPEER2_BUILDER_BASE=debian:10

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_NETOPEER2_BUILDER_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy make pkg-config curl git cmake libssh-4 libssh-dev libpcre3-dev quilt

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
