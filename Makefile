.PHONY: docker-image bash init south onlp openconfig-converter docker yang

ifndef DOCKER_CMD
    DOCKER_CMD=bash
endif

ifndef DOCKER_IMAGE
    DOCKER_IMAGE=sysrepo-builder
endif

all: north south

docker:
	DOCKER_CMD='make' $(MAKE) cmd

ifndef SYSREPO_IMAGE
    SYSREPO_IMAGE := sysrepo
endif

docker-image:
	docker build $(DOCKER_BUILD_OPTION) -t sysrepo-builder .

docker-run-image:
	docker build $(DOCKER_BUILD_OPTION) -f Dockerfile.run -t sysrepo .

docker-yang-generator-image:
	docker build $(DOCKER_BUILD_OPTION) -f Dockerfile.clang -t yang-generator .

yang: yang/goldstone-tai.yang

yang/goldstone-tai.yang:
	docker run -it -v `pwd`:/data -w /data yang-generator bash -c './tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h | pyang -f yang > /data/$@'

bash:
	$(MAKE) cmd

cmd:
	docker run --net host -it -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform --privileged --rm $(DOCKER_IMAGE) $(DOCKER_CMD)

init:
	$(RM) -r `sysrepoctl -l | head -n 1 | cut -d ':' -f 2` /dev/shm/sr*
	sysrepoctl -s /data/yang --install /data/yang/goldstone-onlp.yang
	sysrepoctl -s /data/yang --install /data/yang/goldstone-tai.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-types.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-fan.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-psu.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/system/openconfig-alarm-types.yang

south: onlp openconfig-converter tai
north: cli

onlp:
	$(MAKE) -C src/south/onlp

openconfig-converter:
	$(MAKE) -C src/south/openconfig-converter

tai:
	$(MAKE) -C src/south/tai

cli:
	$(MAKE) -C src/north/cli

clean:
	$(MAKE) -C src/south/onlp clean
	$(MAKE) -C src/south/openconfig-converter clean
	$(MAKE) -C src/south/tai clean
	$(MAKE) -C src/north/cli clean
