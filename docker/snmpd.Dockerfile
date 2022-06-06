# syntax=docker/dockerfile:1.4

ARG GS_SNMP_BASE=debian:10

ARG http_proxy
ARG https_proxy

FROM $GS_SNMP_BASE AS snmpd

RUN --mount=type=cache,target=/var/cache/apt,sharing=private --mount=type=cache,target=/var/lib/apt,sharing=private \
            apt update && DEBIAN_FRONTEND=noninteractive apt install --no-install-recommends -qy snmpd snmp
