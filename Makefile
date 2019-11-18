.PHONY: docker-image bash init south onlp openconfig-converter docker

ifndef DOCKER_CMD
    DOCKER_CMD=bash
endif

ifndef DOCKER_IMAGE
    DOCKER_IMAGE=sysrepo-builder
endif

docker:
	DOCKER_CMD='make north' $(MAKE) cmd
	DOCKER_CMD='make south' $(MAKE) cmd

ifndef SYSREPO_IMAGE
    SYSREPO_IMAGE := sysrepo
endif

all: init south north
	./src/south/onlp/main

docker-image:
	docker build -t sysrepo-builder .

docker-run-image:
	docker build -f Dockerfile.run -t sysrepo .

bash:
	$(MAKE) cmd

cmd:
	docker run --net host -it -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform --privileged --rm $(DOCKER_IMAGE) $(DOCKER_CMD)

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

clean:
	$(MAKE) -C src/south/onlp clean
	$(MAKE) -C src/south/openconfig-converter clean
	$(MAKE) -C src/north/cli clean
