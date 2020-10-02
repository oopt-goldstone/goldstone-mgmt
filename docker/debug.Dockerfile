# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-builder:latest
ARG GS_MGMT_IMAGE=docker.io/microsonic/gs-mgmt:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_IMAGE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy strace gdb iproute2 valgrind libpcre3-dev

RUN --mount=type=bind,from=builder,source=/usr/share/onlp,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | xargs dpkg -i
