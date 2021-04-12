.PHONY: builder bash init yang base-image images docker cli system

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

ifndef GS_MGMT_SONIC_IMAGE
    GS_MGMT_SONIC_IMAGE := gs-mgmt-south-sonic
endif

ifndef GS_MGMT_TAI_IMAGE
    GS_MGMT_TAI_IMAGE := gs-mgmt-south-tai
endif

ifndef GS_MGMT_ONLP_IMAGE
    GS_MGMT_ONLP_IMAGE := gs-mgmt-south-onlp
endif

ifndef GS_MGMT_SYSTEM_IMAGE
    GS_MGMT_SYSTEM_IMAGE := gs-mgmt-south-system
endif

ifndef GS_MGMT_CLI_IMAGE
    GS_MGMT_CLI_IMAGE := gs-mgmt-north-cli
endif

ifndef GS_MGMT_SNMP_IMAGE
    GS_MGMT_SNMP_IMAGE := gs-mgmt-north-snmp
endif

ifndef GS_MGMT_SNMPD_IMAGE
    GS_MGMT_SNMPD_IMAGE := gs-mgmt-snmpd
endif

ifndef GS_MGMT_OC_IMAGE
    GS_MGMT_OC_IMAGE := gs-mgmt-xlate-openconfig
endif

ifndef GS_MGMT_IMAGE_TAG
    GS_MGMT_IMAGE_TAG := latest
endif

ifndef ONL_REPO
    ONL_REPO := sm/OpenNetworkLinux/REPO/stretch/packages/binary-amd64
endif

ifndef ONLP_PACKAGES
    ONLP_PACKAGES := onlp onlp-dev onlp-x86-64-kvm-x86-64-r0 onlp-py3
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
    SONIC_YANG_REPO := /usr/local/sonic
endif

ifndef TAI_META_CUSTOM_FILES
    TAI_META_CUSTOM_FILES := $(abspath $(wildcard scripts/tai/*))
endif

all: builder np2 snmpd base-image images

docker:
	DOCKER_RUN_OPTION="-u `id -u`:`id -g` -e VERBOSE=$(VERBOSE)" DOCKER_CMD='make cli system' $(MAKE) cmd

builder: $(ONLP_DEBS)
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) --build-arg ONL_REPO=$(ONL_REPO) -f docker/builder.Dockerfile -t $(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) .

$(ONLP_DEBS):
	cd sm/OpenNetworkLinux && docker/tools/onlbuilder -9 --non-interactive --isolate -c "bash -c '../../tools/build_onlp.sh'"

base-image:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/run.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) .

images: south-images north-images xlate-images

south-images: south-sonic south-tai south-onlp south-system

north-images: north-cli north-snmp

xlate-images: xlate-openconfig

south-sonic:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/south-sonic.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_SONIC_IMAGE):$(GS_MGMT_IMAGE_TAG) .

south-tai:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/south-tai.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_TAI_IMAGE):$(GS_MGMT_IMAGE_TAG) .

south-onlp:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/south-onlp.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_ONLP_IMAGE):$(GS_MGMT_IMAGE_TAG) .

south-system:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/south-system.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_SYSTEM_IMAGE):$(GS_MGMT_IMAGE_TAG) .

north-cli:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/north-cli.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_CLI_IMAGE):$(GS_MGMT_IMAGE_TAG) .

north-snmp:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/north-snmp.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_SNMP_IMAGE):$(GS_MGMT_IMAGE_TAG) .

xlate-openconfig:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/xlate-openconfig.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_OC_IMAGE):$(GS_MGMT_IMAGE_TAG) .



np2:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/netopeer2.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_NP2_IMAGE):$(GS_MGMT_IMAGE_TAG) .

snmpd:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/snmpd.Dockerfile \
							      -t $(DOCKER_REPO)/$(GS_MGMT_SNMPD_IMAGE):$(GS_MGMT_IMAGE_TAG) .

tester: np2
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f ci/docker/gs-mgmt-test.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_NP2_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t gs-mgmt-test ci

yang: yang/goldstone-tai.yang

yang/goldstone-tai.yang: ./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h $(TAI_META_CUSTOM_FILES)
	./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h $(TAI_META_CUSTOM_FILES) | pyang -f yang > /data/$@

bash:
	DOCKER_RUN_OPTION='-it --cap-add IPC_OWNER --cap-add IPC_LOCK' $(MAKE) cmd

cmd:
	docker run $(DOCKER_RUN_OPTION) -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform $(DOCKER_IMAGE) $(DOCKER_CMD)

cli:
	cd src/north/cli && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist

system:
	cd src/south/system && python setup.py bdist_wheel && pip wheel -r requirements.txt -w dist

init:
	$(RM) -r `sysrepoctl -l | head -n 1 | cut -d ':' -f 2`/* /dev/shm/sr*
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-onlp.yang
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-tai.yang
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-interfaces.yang
	sysrepoctl -s $(GS_YANG_REPO) --install $(GS_YANG_REPO)/goldstone-vlan.yang
	sysrepoctl -s $(OC_YANG_REPO) --install $(OC_YANG_REPO)/platform/openconfig-platform.yang
	sysrepoctl -s $(OC_YANG_REPO):$(OC_YANG_REPO)/../../third_party/ietf --install $(OC_YANG_REPO)/interfaces/openconfig-interfaces.yang
