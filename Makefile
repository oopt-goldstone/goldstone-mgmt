.PHONY: builder bash init south onlp openconfig-converter docker yang

ifndef DOCKER_CMD
    DOCKER_CMD=bash
endif

ifndef GS_MGMT_BUILDER_IMAGE
    GS_MGMT_BUILDER_IMAGE=gs-mgmt-builder
endif

ifndef GS_MGMT_IMAGE
    GS_MGMT_IMAGE := gs-mgmt
endif

ifndef GS_MGMT_DEBUG_IMAGE
    GS_MGMT_DEBUG_IMAGE := gs-mgmt-debug
endif

ifndef GS_MGMT_NP2_IMAGE
    GS_MGMT_NP2_IMAGE := gs-mgmt-netopeer2
endif

ifndef GS_MGMT_IMAGE_TAG
    GS_MGMT_IMAGE_TAG := latest
endif

ifndef ONL_REPO
    ONL_REPO := sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64
endif

ifndef ONLP_PACKAGES
    ONLP_PACKAGES := onlp onlpdev onlp-x86-64-kvm-x86-64-r0
endif

ifndef ONLP_DEBS
    ONLP_DEBS := $(foreach repo,$(ONLP_PACKAGES),$(ONL_REPO)/$(repo)_1.0.0_amd64.deb)
endif

ifndef DOCKER_REPO
    DOCKER_REPO := docker.io/microsonic
endif

ifndef DOCKER_IMAGE
    DOCKER_IMAGE := $(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG)
endif

ifndef GS_YANG_REPO
    GS_YANG_REPO := /data/yang
endif

ifndef OC_YANG_REPO
    OC_YANG_REPO := /data/sm/openconfig/release/models
endif

ifndef SONIC_YANG_REPO
    SONIC_YANG_REPO := /data/sm/sonic-mgmt-common/models/yang/sonic
endif

all: builder np2 docker image debug-image

docker:
	DOCKER_RUN_OPTION="-u `id -u`:`id -g` -e VERBOSE=$(VERBOSE)" DOCKER_CMD='make yang south' $(MAKE) cmd

builder: $(ONLP_DEBS) patch
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) --build-arg ONL_REPO=$(ONL_REPO) -f docker/builder.Dockerfile -t $(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) .

$(ONLP_DEBS):
	cd sm/OpenNetworkLinux && docker/tools/onlbuilder -9 --non-interactive --isolate -c "bash -c '../../tools/build_onlp.sh'"

image:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/run.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) .

debug-image:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/debug.Dockerfile \
							      --build-arg GS_MGMT_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_DEBUG_IMAGE):$(GS_MGMT_IMAGE_TAG) .

np2: patch
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/netopeer2.Dockerfile \
							      -t $(DOCKER_REPO)/$(GS_MGMT_NP2_IMAGE):$(GS_MGMT_IMAGE_TAG) .

patch:
	quilt push -a || [ $$? -eq 2 ] && true

yang: yang/goldstone-tai.yang

yang/goldstone-tai.yang: ./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h
	./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h | pyang -f yang > /data/$@

bash:
	DOCKER_RUN_OPTION='-it --cap-add IPC_OWNER --cap-add IPC_LOCK' $(MAKE) cmd

cmd:
	docker run $(DOCKER_RUN_OPTION) -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform $(DOCKER_IMAGE) $(DOCKER_CMD)

init:
	$(RM) -r `sysrepoctl -l | head -n 1 | cut -d ':' -f 2`/* /dev/shm/sr*
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-onlp.yang
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-tai.yang
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-sonic-interface.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/platform/openconfig-platform-types.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/platform/openconfig-platform.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/platform/openconfig-platform-fan.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/platform/openconfig-platform-psu.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/system/openconfig-alarm-types.yang

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
