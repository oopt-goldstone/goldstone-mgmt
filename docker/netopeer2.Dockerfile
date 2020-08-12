# syntax=docker/dockerfile:experimental

# ubuntu:20.04's libssh won't work
ARG GS_NETOPEER2_BUILDER_BASE=ubuntu:18.04

ARG http_proxy
ARG https_proxy

FROM $GS_NETOPEER2_BUILDER_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy make pkg-config curl git cmake libssh-4 libssh-dev libpcre3-dev quilt

RUN --mount=type=bind,source=sm/libyang,target=/src mkdir -p /build/libyang && cd /build/libyang && \
            cmake /src && cmake --build . && cmake --install . && make install && ldconfig

RUN --mount=type=bind,source=sm/sysrepo,target=/root/sm/sysrepo,rw \
    --mount=type=bind,source=patches/sysrepo,target=/root/patches \
    cd /root && quilt push -a && mkdir -p /build/sysrepo && cd /build/sysrepo && \
    cmake -DREPO_PATH=/var/lib/sysrepo/ /root/sm/sysrepo && make && make install

RUN --mount=type=bind,source=sm/libnetconf2,target=/root/sm/libnetconf2,rw cd /root && mkdir -p /build/libnetconf2 && cd /build/libnetconf2 && \
            cmake /root/sm/libnetconf2 && make && make install

RUN --mount=type=bind,source=sm/netopeer2,target=/root/sm/netopeer2,rw \
    --mount=type=bind,source=patches/np2,target=/root/patches \
    cd /root && rm -rf .pc && quilt push -a && mkdir -p /build/netopeer2 && cd /build/netopeer2 && \
    cmake /root/sm/netopeer2 && make && make install && mkdir -p /usr/local/share/netopeer2 && cp -r /root/sm/netopeer2/scripts /usr/local/share/netopeer2

RUN ldconfig
