FROM ubuntu:18.04 AS grpc

RUN apt update && apt install -qy g++ make git dh-autoreconf pkg-config
RUN git clone https://github.com/grpc/grpc.git && cd grpc; git submodule update --init --recursive; make install; cd third_party/protobuf; make install

FROM grpc AS grpc-tmp

RUN rm `find /usr/local/lib -type l`
RUN rm `find /usr/lib/x86_64-linux-gnu -type l`

FROM ubuntu:18.04 AS swig

RUN apt update && apt install -qy g++ make bison automake git libpcre3 libpcre3-dev
RUN git clone https://github.com/swig/swig.git && cd swig && ./autogen.sh && ./configure && make && make install

FROM ubuntu:18.04 AS cmake

RUN apt update && apt install -qy wget
RUN wget https://github.com/Kitware/CMake/releases/download/v3.16.0-rc3/cmake-3.16.0-rc3-Linux-x86_64.tar.gz \
        && tar xvf cmake-3.16.0-rc3-Linux-x86_64.tar.gz

#FROM ubuntu:18.04 AS python3.8
##
#RUN apt update && apt install -qy wget build-essential libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev libffi-dev uuid-dev
#RUN cd Python-3.8.0 && ./configure --enable-shared  && make -j `nproc`

FROM ubuntu:18.04

RUN apt update && apt install -qy git libpcre3-dev vim pkg-config bison
RUN apt update && apt install -qy wget build-essential libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev libffi-dev uuid-dev

RUN wget https://www.python.org/ftp/python/3.8.0/Python-3.8.0.tar.xz && tar xf Python-3.8.0.tar.xz
RUN cd Python-3.8.0 && ./configure --enable-shared && make -j `nproc` && make install && ldconfig

RUN update-alternatives --install /usr/bin/python python /usr/local/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/local/bin/pip3 10
RUN pip install --upgrade pip

COPY --from=cmake /cmake-3.16.0-rc3-Linux-x86_64/bin/* /usr/bin/
COPY --from=cmake /cmake-3.16.0-rc3-Linux-x86_64/share/cmake-3.16 /usr/share/cmake-3.16

COPY --from=grpc-tmp /usr/local/lib/libgrpc* /usr/local/lib/
COPY --from=grpc-tmp /usr/local/lib/libgpr* /usr/local/lib/
COPY --from=grpc-tmp /usr/local/lib/libproto* /usr/local/lib/

COPY --from=grpc-tmp /usr/local/bin/* /usr/local/bin/
COPY --from=grpc-tmp /usr/local/include/google /usr/local/include/google
COPY --from=grpc-tmp /usr/local/include/grpc   /usr/local/include/grpc
COPY --from=grpc-tmp /usr/local/include/grpc++ /usr/local/include/grpc++
COPY --from=grpc-tmp /usr/local/include/grpcpp /usr/local/include/grpcpp
COPY --from=grpc-tmp /usr/local/lib/pkgconfig/* /usr/local/lib/pkgconfig/

COPY --from=swig /usr/local/bin/ccache-swig /usr/local/bin/
COPY --from=swig /usr/local/bin/swig /usr/local/bin/
COPY --from=swig /usr/local/share/swig /usr/local/share/swig

RUN ldconfig

ADD sm/libyang libyang
RUN rm -rf libyang/builds && mkdir -p libyang/builds && cd libyang/builds && ls ../ && cmake -DGEN_LANGUAGE_BINDINGS=ON -DGEN_CPP_BINDINGS=ON -DGEN_PYTHON_BINDINGS=ON -DGEN_PYTHON_VERSION=3 .. && cmake --build . && cmake --install .
ADD sm/sysrepo sysrepo
RUN mkdir -p /var/lib/sysrepo
RUN rm -rf sysrepo/builds && mkdir -p sysrepo/builds && cd sysrepo/builds && cmake -DGEN_CPP_BINDINGS=ON -DREPO_PATH=/var/lib/sysrepo/ .. && make && make install
RUN mkdir -p /usr/local/include/utils && cp sysrepo/src/utils/xpath.h /usr/local/include/utils/

#RUN cd sysrepo/swig/python && make clean && make _sysrepo.so
#RUN cp sysrepo/swig/python/sysrepo.py /usr/lib/python3/dist-packages/
#RUN cp sysrepo/swig/python/_sysrepo.so /usr/lib/python3/dist-packages/

ADD onlp/libonlp.so /lib/x86_64-linux-gnu/
ADD onlp/libonlp-platform.so /lib/x86_64-linux-gnu/
ADD onlp/libonlp-platform-defaults.so /lib/x86_64-linux-gnu/
ADD onlp/AIM /usr/local/include/AIM
ADD onlp/onlp /usr/local/include/onlp
ADD onlp/onlplib /usr/local/include/onlplib
ADD onlp/IOF /usr/local/include/IOF

RUN ldconfig
RUN ln -s libonlp-platform.so /lib/x86_64-linux-gnu/libonlp-platform.so.1

RUN pip install pyang
