ARG GS_MGMT_BUILDER_IMAGE=ghcr.io/oopt-goldstone/goldstone-mgmt/gs-mgmt-builder:latest

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

RUN --mount=type=bind,source=src/north/cli,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/cli && cp dist/*.whl /usr/share/wheels/cli

RUN --mount=type=bind,source=src/south/system,target=/src,rw \
    cd /src && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist \
    && mkdir -p /usr/share/wheels/system && cp dist/*.whl /usr/share/wheels/system
