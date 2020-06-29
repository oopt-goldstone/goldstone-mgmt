# syntax=docker/dockerfile:experimental

ARG GS_MGMT=gs-mgmt:latest

FROM $GS_MGMT

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && apt install -qy strace
