FROM ubuntu:18.04

RUN apt update && apt install -qy gcc make git cmake libpcre3-dev swig g++ python3 libpython3-dev python3-pip python3-distutils vim
RUN pip3 install prompt_toolkit

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 10


ADD sm/libyang libyang
RUN rm -rf libyang/builds && mkdir -p libyang/builds && cd libyang/builds && ls ../ && cmake -DGEN_LANGUAGE_BINDINGS=ON -DGEN_CPP_BINDINGS=ON -DGEN_PYTHON_BINDINGS=ON -DGEN_PYTHON_VERSION=3 .. && make && make install
ADD sm/sysrepo sysrepo
RUN rm -rf sysrepo/builds && mkdir -p sysrepo/builds && cd sysrepo/builds && cmake -DGEN_CPP_BINDINGS=ON .. && make && make install
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

