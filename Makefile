.PHONY: docker-image bash init south onlp openconfig-converter

ifndef SYSREPO_IMAGE
    SYSREPO_IMAGE := sysrepo
endif

all: init south north
	./src/south/onlp/main

docker-image:
	docker build -t sysrepo .

bash:
	docker run --net host -it -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform --privileged --rm --name sysrepo $(SYSREPO_IMAGE) bash

init:
	$(RM) -r /sysrepo/builds/repository/ /dev/shm/sr*
	sysrepoctl -s /data/yang --install /data/yang/goldstone-onlp.yang
	sysrepoctl -s /data/yang --install /data/yang/goldstone-tai.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-types.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-fan.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-psu.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/system/openconfig-alarm-types.yang

south: onlp openconfig-converter
north: cli

onlp:
	$(MAKE) -C src/south/onlp

openconfig-converter:
	$(MAKE) -C src/south/openconfig-converter

cli:
	$(MAKE) -C src/north/cli

.PHONY: test

test:
	g++ -g -std=c++11 -o test test.cpp -lyang-cpp -lyang
	LD_LIBRARY_PATH=/usr/local/lib ./test
