# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_BASE=debian:10

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BUILDER_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy libgrpc++-dev g++ protobuf-compiler-grpc make pkg-config python3 curl python3-distutils python3-pip libclang1-6.0 doxygen libi2c-dev git python3-dev cmake libpcre3-dev bison graphviz libcmocka-dev valgrind quilt libcurl4-gnutls-dev swig debhelper devscripts libpam-dev autoconf-archive libssl-dev

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN --mount=type=bind,source=sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64,target=/src mkdir -p /usr/share/onlp && cp /src/onlp_1.0.0_amd64.deb /src/onlp-dev_1.0.0_amd64.deb /src/onlp-x86-64-kvm-x86-64-r0_1.0.0_amd64.deb /src/onlp-py3_1.0.0_amd64.deb /usr/share/onlp/
RUN dpkg -i /usr/share/onlp/*.deb

RUN --mount=type=bind,source=sm/libyang,target=/root/sm/libyang,rw \
    --mount=type=bind,source=patches/libyang,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    mkdir -p /root/sm/libyang/build && cd /root/sm/libyang/build && \
    cmake .. && make build-deb && mkdir -p /usr/share/debs/libyang && cp debs/* /usr/share/debs/libyang/

RUN dpkg -i /usr/share/debs/libyang/*.deb

RUN --mount=type=bind,source=sm/sysrepo,target=/root/sm/sysrepo,rw \
    --mount=type=bind,source=patches/sysrepo,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /root/sm/sysrepo/build && cd /root/sm/sysrepo/build && \
    cmake -DREPO_PATH=/var/lib/sysrepo/ .. && make build-deb && mkdir -p /usr/share/debs/sysrepo && cp debs/* /usr/share/debs/sysrepo/ && \
    mkdir -p /usr/local/include/utils && cp /root/sm/sysrepo/src/utils/xpath.h /usr/local/include/utils/

RUN dpkg -i /usr/share/debs/sysrepo/*.deb

RUN --mount=type=bind,source=sm/sonic-mgmt-common,target=/root/sm/sonic-mgmt-common,rw \
    --mount=type=bind,source=patches/sonic-mgmt,target=/root/patches \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /usr/local/sonic/ && cp -r /root/sm/sonic-mgmt-common/models/yang/sonic/* /usr/local/sonic/ && ls /usr/local/sonic/

RUN pip install pyang clang jinja2 prompt_toolkit wheel

RUN mkdir -p /usr/share/wheels

RUN --mount=type=bind,source=sm/libyang-python,target=/root/sm/libyang-python,rw \
    --mount=type=bind,source=patches/libyang-python,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/libyang-python && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels/

RUN --mount=type=bind,source=sm/sysrepo-python,target=/root/sm/sysrepo-python,rw \
    --mount=type=bind,source=patches/sysrepo-python,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/sysrepo-python && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels/

RUN --mount=type=bind,source=sm/pam_tacplus,target=/root/sm/pam_tacplus,rw \
    --mount=type=bind,source=patches/pam,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/pam_tacplus && dpkg-buildpackage -rfakeroot -b -us -uc

RUN dpkg -i /root/sm/libtac2_1.4.1-1_amd64.deb
RUN dpkg -i /root/sm/libtac-dev_1.4.1-1_amd64.deb

RUN --mount=type=bind,source=sm/libnss-tacplus,target=/root/sm/libnss-tacplus,rw \
    --mount=type=bind,source=patches/nss,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && \
    cd /root/sm/libnss-tacplus && dpkg-buildpackage -rfakeroot -b -us -uc && \
    cd /root/sm && mkdir -p /usr/share/debs/tacacs && cp *.deb /usr/share/debs/tacacs/

RUN pip install grpcio-tools grpclib

RUN --mount=type=bind,source=sm/oopt-tai,target=/root/sm/oopt-tai,rw \
    cd /root/sm/oopt-tai/tools/taish && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels/

RUN pip install /usr/share/wheels/*.whl

RUN --mount=type=bind,source=src/north/cli,target=/src,rw \
    cd /src && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels

RUN --mount=type=bind,source=src/south/system,target=/src/south/system,rw \
    cd /src/south/system && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels

RUN --mount=type=bind,source=scripts,target=/src,rw \
    cd /src && cp /src/reload.sh /usr/local/bin/

ADD sm/oopt-tai/meta/main.py /usr/local/lib/python3.7/dist-packages/tai.py
