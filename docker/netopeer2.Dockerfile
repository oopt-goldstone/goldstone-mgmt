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

RUN --mount=type=bind,source=sm/sysrepo,target=/root/sm/sysrepo,rw --mount=type=bind,source=patches,target=/root/patches cd /root && ls && quilt push -a && mkdir -p /build/sysrepo && cd /build/sysrepo && \
            cmake -DREPO_PATH=/var/lib/sysrepo/ /root/sm/sysrepo && make && make install

RUN --mount=type=tmpfs,target=/opt cd /opt && git clone https://github.com/CESNET/libnetconf2.git && cd libnetconf2 && mkdir build && cd build && cmake .. && make && make install
RUN --mount=type=tmpfs,target=/opt cd /opt && git clone -b devel https://github.com/CESNET/netopeer2.git && cd netopeer2 && mkdir build && cd build && cmake .. && make && make install && mkdir -p /usr/local/share/netopeer2 && cp -r ../scripts /usr/local/share/netopeer2

RUN ldconfig
