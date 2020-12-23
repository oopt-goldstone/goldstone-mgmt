# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-netopeer2:latest

FROM $GS_MGMT_BUILDER_IMAGE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy --no-install-recommends python3 python3-pip python3-setuptools

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN pip install --upgrade pip

RUN pip install paramiko scp black pyang

COPY --from=docker:19.03 /usr/local/bin/docker /usr/local/bin/
