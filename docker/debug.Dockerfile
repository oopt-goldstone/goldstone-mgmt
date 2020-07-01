# syntax=docker/dockerfile:experimental

ARG GS_MGMT_IMAGE=gs-mgmt:latest

FROM $GS_MGMT_IMAGE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy strace gdb iproute2 valgrind
