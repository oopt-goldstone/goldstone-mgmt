# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_IMAGE=docker.io/microsonic/gs-mgmt-builder:latest
ARG GS_MGMT_BASE=debian:10

FROM $GS_MGMT_BUILDER_IMAGE as builder

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && apt install -qy python3 vim curl python3-pip libgrpc++1 libcurl4-gnutls-dev iputils-ping traceroute

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN --mount=type=bind,from=builder,source=/usr/share/onlp,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/libyang,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

RUN --mount=type=bind,from=builder,source=/usr/share/debs/sysrepo,target=/src ls /src/*.deb | awk '$0 !~ /python/ && $0 !~ /-dbg_/ && $0 !~ /-dev_/ { print $0 }' | xargs dpkg -i

ENV PYTHONPATH /usr/lib/python3/dist-packages

RUN --mount=type=bind,source=src/north/cli,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/south/system,target=/src,rw pip install /src

RUN --mount=type=bind,from=builder,source=/usr/share/wheels,target=/usr/share/wheels \
            pip install /usr/share/wheels/*.whl

RUN --mount=type=bind,source=sm/sonic-py-swsssdk,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/south/taipy,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/south/onlppy,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/south/sonicpy,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/north/cli,target=/src,rw pip install /src

RUN --mount=type=bind,source=src/north/snmp,target=/src,rw pip install /src

COPY yang /var/lib/goldstone/yang/gs/
ENV GS_YANG_REPO /var/lib/goldstone/yang/gs
COPY sm/openconfig/release/models/ /var/lib/goldstone/yang/oc/
ENV OC_YANG_REPO /var/lib/goldstone/yang/oc
COPY --from=builder /usr/local/sonic/  /var/lib/goldstone/yang/sonic/
ENV SONIC_YANG_REPO /var/lib/goldstone/yang/sonic

RUN --mount=type=bind,source=scripts,target=/src,rw \
    cd /src && cp /src/reload.sh /usr/local/bin/

# vim:filetype=dockerfile
