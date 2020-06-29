.PHONY: builder bash init south onlp openconfig-converter docker yang

ifndef DOCKER_CMD
    DOCKER_CMD=bash
endif

ifndef DOCKER_BUILDER_IMAGE
    DOCKER_BUILDER_IMAGE=gs-mgmt-builder
endif

ifndef DOCKER_IMAGE
    DOCKER_IMAGE := gs-mgmt
endif

ifndef DOCKER_DEBUG_IMAGE
    DOCKER_DEBUG_IMAGE := gs-mgmt-debug
endif

ifndef ONL_REPO
    ONL_REPO := sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64
endif

ifndef ONLP_DEBS
    ONLP_DEBS := $(foreach repo,onlp onlp-dev,$(ONL_REPO)/$(repo)_1.0.0_amd64.deb)
endif

ifndef DOCKER_REPO
    DOCKER_REPO := docker.io/library
endif

ifndef DOCKER_IMAGE_TAG
    DOCKER_IMAGE_TAG := latest
endif

all: image

docker:
	DOCKER_RUN_OPTION="-u `id -u`:`id -g`" DOCKER_CMD='make yang south' $(MAKE) cmd

builder: $(ONLP_DEBS)
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) --build-arg ONL_REPO=$(ONL_REPO) -f docker/builder.Dockerfile -t $(DOCKER_REPO)/$(DOCKER_BUILDER_IMAGE):$(DOCKER_IMAGE_TAG) .

$(ONLP_DEBS):
	cd sm/OpenNetworkLinux && docker/tools/onlbuilder -9 --non-interactive --isolate -c "bash -c '../../tools/build_onlp.sh'"

image: builder docker
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/run.Dockerfile -t $(DOCKER_REPO)/$(DOCKER_IMAGE):$(DOCKER_IMAGE_TAG) .

debug-image: image
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/debug.Dockerfile -t $(DOCKER_REPO)/$(DOCKER_DEBUG_IMAGE):$(DOCKER_IMAGE_TAG) .

yang: yang/goldstone-tai.yang

yang/goldstone-tai.yang: ./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h
	./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h | pyang -f yang > /data/$@

bash:
	DOCKER_RUN_OPTION='-it --cap-add IPC_OWNER --cap-add IPC_LOCK' $(MAKE) cmd

cmd:
	docker run $(DOCKER_RUN_OPTION) -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform $(DOCKER_REPO)/$(DOCKER_BUILDER_IMAGE):$(DOCKER_IMAGE_TAG) $(DOCKER_CMD)

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
