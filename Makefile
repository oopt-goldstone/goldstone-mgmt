.PHONY: builder bash init yang base-image images docker cli system

ARCH ?= amd64

DOCKER_CMD ?= bash

GS_MGMT_BUILDER_IMAGE ?= gs-mgmt-builder
GS_MGMT_IMAGE ?= gs-mgmt
GS_MGMT_DEBUG_IMAGE ?= gs-mgmt-debug
GS_MGMT_NP2_IMAGE ?= gs-mgmt-netopeer2
GS_MGMT_SONIC_IMAGE ?= gs-mgmt-south-sonic
GS_MGMT_TAI_IMAGE ?= gs-mgmt-south-tai
GS_MGMT_ONLP_IMAGE ?= gs-mgmt-south-onlp
GS_MGMT_SYSTEM_IMAGE ?= gs-mgmt-south-system
GS_MGMT_CLI_IMAGE ?= gs-mgmt-north-cli
GS_MGMT_SNMP_IMAGE ?= gs-mgmt-north-snmp
GS_MGMT_SNMPD_IMAGE ?= gs-mgmt-snmpd
GS_MGMT_OC_IMAGE ?= gs-mgmt-xlate-openconfig
GS_MGMT_NOTIF_IMAGE ?= gs-mgmt-south-notif

GS_MGMT_IMAGE_TAG ?= latest-$(ARCH)

ONL_REPO ?= sm/OpenNetworkLinux/REPO/stretch/packages/binary-$(ARCH)

ifeq ($(ARCH), amd64)
    ONLP_PACKAGES ?= onlp onlp-dev onlp-x86-64-kvm-x86-64-r0 onlp-py3
else ifeq ($(ARCH), arm64)
    ONLP_PACKAGES ?= onlp onlp-dev onlp-arm64-wistron-wtp-01-c1-00-r0 onlp-py3
endif

ONLP_DEBS ?= $(foreach repo,$(ONLP_PACKAGES),$(ONL_REPO)/$(repo)_1.0.0_$(ARCH).deb)

DOCKER_REPO ?= docker.io/microsonic
DOCKER_IMAGE ?= $(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG)

GS_YANG_REPO ?= /data/yang
OC_YANG_REPO ?= /data/sm/openconfig/release/models
SONIC_YANG_REPO ?= /usr/local/sonic

TAI_META_CUSTOM_FILES ?= $(abspath $(wildcard scripts/tai/*))

DOCKER_BUILD_OPTION ?= --platform linux/$(ARCH)

all: builder np2 snmpd base-image images

docker:
	DOCKER_RUN_OPTION="-u `id -u`:`id -g` -e VERBOSE=$(VERBOSE)" DOCKER_CMD='make cli system' $(MAKE) cmd

builder: $(ONLP_DEBS)
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) --build-arg ONL_REPO=$(ONL_REPO) -f docker/builder.Dockerfile -t $(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) .

onlp: $(ONLP_DEBS)


$(ONLP_DEBS):
	cd sm/OpenNetworkLinux && docker/tools/onlbuilder -9 --non-interactive --isolate -c "../../tools/build_onlp.sh $(ARCH)"

base-image:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/run.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) .

images: south-images north-images xlate-images

south-images: south-sonic south-tai south-onlp south-system south-notif

north-images: north-cli north-snmp np2

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
south-notif:
	DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/south-notif.Dockerfile \
							      --build-arg GS_MGMT_BUILDER_IMAGE=$(DOCKER_REPO)/$(GS_MGMT_BUILDER_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      --build-arg GS_MGMT_BASE=$(DOCKER_REPO)/$(GS_MGMT_IMAGE):$(GS_MGMT_IMAGE_TAG) \
							      -t $(DOCKER_REPO)/$(GS_MGMT_NOTIF_IMAGE):$(GS_MGMT_IMAGE_TAG) .
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

lint:
	exit `black -q --diff --exclude src/north/snmp/src src | wc -l`
	pyang -p /usr/local/share/yang/modules/ietf yang/*.yang
	grep -rnI 'print(' src || exit 0 && exit 1
