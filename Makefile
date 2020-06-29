.PHONY: docker-image bash init south onlp openconfig-converter docker yang

ifndef DOCKER_CMD
    DOCKER_CMD=bash
endif

ifndef DOCKER_IMAGE
    DOCKER_IMAGE=sysrepo-builder
endif

all: south

docker:
	DOCKER_CMD='make' $(MAKE) cmd

ifndef SYSREPO_IMAGE
    SYSREPO_IMAGE := sysrepo
endif

ifndef ONL_REPO
    ONL_REPO := sm/OpenNetworkLinux/REPO/buster/packages/binary-amd64
endif

builder: $(ONL_REPO)/onlp_1.0.0_amd64.deb $(ONL_REPO)/onlp-dev_1.0.0_amd64.deb
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) --build-arg ONL_REPO=$(ONL_REPO) -f docker/builder.Dockerfile -t sysrepo-builder .

$(ONL_REPO)/onlp_1.0.0_amd64.deb $(ONL_REPO)/onlp-dev_1.0.0_amd64.deb:
	@cd sm/OpenNetworkLinux && docker/tools/onlbuilder --image gs-builder --isolate -c "bash -c '../../tools/build_onlp.sh'"

image:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/run.Dockerfile -t sysrepo .

yang: yang/goldstone-tai.yang

yang/goldstone-tai.yang: ./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h
	docker run -it -v `pwd`:/data -w /data $(DOCKER_IMAGE) bash -c 'PYTHONPATH=/usr/local/lib/python3.8/ ./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h | pyang -f yang > /data/$@'

bash:
	$(MAKE) cmd

cmd:
	docker run ${DOCKER_RUN_OPTION} -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform $(DOCKER_IMAGE) $(DOCKER_CMD)

init:
	$(RM) -r `sysrepoctl -l | head -n 1 | cut -d ':' -f 2` /dev/shm/sr*
	sysrepoctl -s /data/yang --install /data/yang/goldstone-onlp.yang
	sysrepoctl -s /data/yang --install /data/yang/goldstone-tai.yang
	sysrepoctl -s /data/yang --install /data/yang/goldstone-sonic-interface.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-types.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-fan.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/platform/openconfig-platform-psu.yang
	sysrepoctl -s /data/sm/openconfig/  --install /data/sm/openconfig/release/models/system/openconfig-alarm-types.yang

south: onlp openconfig-converter tai sonic-interface

onlp:
	$(MAKE) -C src/south/onlp

openconfig-converter:
	$(MAKE) -C src/south/openconfig-converter

tai:
	$(MAKE) -C src/south/tai

sonic-interface:
	$(MAKE) -C src/south/sonic-interface


clean:
	$(MAKE) -C src/south/onlp clean
	$(MAKE) -C src/south/openconfig-converter clean
	$(MAKE) -C src/south/tai clean
