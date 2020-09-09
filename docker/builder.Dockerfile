# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_BASE=ubuntu:20.04

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BUILDER_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninteractive apt install -qy libgrpc++-dev g++ protobuf-compiler-grpc make pkg-config python3 curl python3-distutils python3-pip libclang1-6.0 doxygen libi2c-dev git python3-dev cmake libpcre3-dev bison graphviz libcmocka-dev valgrind quilt libcurl4-gnutls-dev swig

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10

RUN --mount=type=bind,source=sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64,target=/src mkdir -p /usr/share/onlp && cp /src/onlp_1.0.0_amd64.deb /src/onlp-dev_1.0.0_amd64.deb /src/onlp-x86-64-kvm-x86-64-r0_1.0.0_amd64.deb /usr/share/onlp/
RUN dpkg -i /usr/share/onlp/*.deb

RUN --mount=type=bind,source=sm/libyang,target=/src mkdir -p /build/libyang && cd /build/libyang && \
            cmake -DGEN_LANGUAGE_BINDINGS=1 -DGEN_CPP_BINDINGS=1 -DGEN_PYTHON_BINDINGS=0 /src && cmake --build . && cmake --install . && make install && ldconfig

RUN --mount=type=bind,source=sm/sysrepo,target=/root/sm/sysrepo,rw \
    --mount=type=bind,source=patches/sysrepo,target=/root/patches \
    --mount=type=tmpfs,target=/root/.pc,rw \
    cd /root && quilt upgrade && quilt push -a && mkdir -p /build/sysrepo && cd /build/sysrepo && \
    cmake -DGEN_LANGUAGE_BINDINGS=ON -DGEN_CPP_BINDINGS=ON -DGEN_PYTHON_BINDINGS=OFF -DREPO_PATH=/var/lib/sysrepo/ /root/sm/sysrepo && make && make install && mkdir -p /usr/local/include/utils && cp /root/sm/sysrepo/src/utils/xpath.h /usr/local/include/utils/ && ldconfig

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

RUN pip install grpcio-tools grpclib

RUN --mount=type=bind,source=sm/oopt-tai,target=/root/sm/oopt-tai,rw \
    cd /root/sm/oopt-tai/tools/taish && python setup.py bdist_wheel && cp dist/*.whl /usr/share/wheels/

RUN pip install /usr/share/wheels/*.whl

ADD sm/oopt-tai/meta/main.py /usr/local/lib/python3.8/dist-packages/tai.py
