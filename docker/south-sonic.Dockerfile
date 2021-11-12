# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

RUN pip install --upgrade pip
RUN pip install wheel grpcio-tools grpclib
RUN --mount=type=bind,source=src/south/sonic,target=/src,rw \
    cd /src && python -m grpc_tools.protoc -Iproto --python_out=. --python_grpc_out=. ./proto/goldstone/south/sonic/bcmd.proto \
    && python setup.py bdist_wheel \
    && mkdir -p /usr/share/wheels/sonic && cp dist/*.whl /usr/share/wheels/sonic

FROM $GS_MGMT_BASE

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,from=builder,source=/usr/share/wheels/sonic,target=/sonic pip install /sonic/*.whl

# vim:filetype=dockerfile
