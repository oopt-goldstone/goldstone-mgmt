# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && apt install -qy --no-install-recommends libdbus-1-3

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/system/*.whl

RUN --mount=type=bind,source=src/south/system,target=/src,rw pip install /src

# vim:filetype=dockerfile
