# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/tai/*.whl

RUN --mount=type=bind,source=src/south/dpll,target=/src,rw pip install /src

# vim:filetype=dockerfile
