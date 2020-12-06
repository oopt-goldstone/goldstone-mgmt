# syntax=docker/dockerfile:experimental

ARG GS_SNMP_BASE=debian:10

ARG http_proxy
ARG https_proxy

FROM $GS_SNMP_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install --no-install-recommends -qy snmpd snmp
