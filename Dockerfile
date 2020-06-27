# syntax=docker/dockerfile:experimental

ARG GS_MGMT_BUILDER_BASE=ubuntu:20.04

ARG http_proxy
ARG https_proxy

FROM $GS_MGMT_BUILDER_BASE

RUN --mount=type=cache,target=/var/cache/apt --mount=type=cache,target=/var/lib/apt \
            apt update && DEBIAN_FRONTEND=noninterative apt install -qy libgrpc++-dev g++ protobuf-compiler-grpc make pkg-config python3 curl python3-distutils libclang1-6.0 doxygen libi2c-dev git python3-dev cmake swig libpcre3-dev bison graphviz libcmocka-dev valgrind

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN curl -kL https://bootstrap.pypa.io/get-pip.py | python
RUN ldconfig

RUN --mount=type=bind,target=/src mkdir -p /build/libyang && cd /build/libyang && \
            cmake -DGEN_LANGUAGE_BINDINGS=ON -DGEN_CPP_BINDINGS=ON -DGEN_PYTHON_BINDINGS=ON -DGEN_PYTHON_VERSION=3 /src/sm/libyang/ && cmake --build . && cmake --install . && make install && ldconfig

RUN --mount=type=bind,target=/src mkdir -p /build/sysrepo && cd /build/sysrepo && \
            cmake -DGEN_LANGUAGE_BINDINGS=ON -DGEN_CPP_BINDINGS=ON -DREPO_PATH=/var/lib/sysrepo/ /src/sm/sysrepo && make && make install && mkdir -p /usr/local/include/utils && cp /src/sm/sysrepo/src/utils/xpath.h /usr/local/include/utils/

ADD onlp/libonlp.so /lib/x86_64-linux-gnu/
ADD onlp/libonlp-platform.so /lib/x86_64-linux-gnu/
ADD onlp/libonlp-platform-defaults.so /lib/x86_64-linux-gnu/
ADD onlp/AIM /usr/local/include/AIM
ADD onlp/onlp /usr/local/include/onlp
ADD onlp/onlplib /usr/local/include/onlplib
ADD onlp/IOF /usr/local/include/IOF

RUN ldconfig
RUN ln -s libonlp-platform.so /lib/x86_64-linux-gnu/libonlp-platform.so.1

RUN pip install pyang clang jinja2 prompt_toolkit

ADD sm/oopt-tai/meta/main.py /usr/local/lib/python3.8/tai.py
