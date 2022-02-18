.PHONY: builder images tester host-packages bash yang

ARCH ?= $(subst x86_64,amd64,$(shell uname -m))

DOCKER_CMD ?= bash
DOCKER_BUILD_OPTION ?= --platform linux/$(ARCH)
DOCKER_IMAGE ?= $(BUILDER)

GS_MGMT_IMAGE_PREFIX ?= ghcr.io/oopt-goldstone/mgmt/
GS_MGMT_IMAGE_TAG ?= latest

define image_name
$(GS_MGMT_IMAGE_PREFIX)$1:$(GS_MGMT_IMAGE_TAG)
endef

BUILDER ?= $(call image_name,builder)

GS_SAVE_AFTER_BUILD ?= 0

define save
if [ $(GS_SAVE_AFTER_BUILD) -eq 1 ]; then mkdir -p builds && docker save $(call image_name,$(1)) > builds/$(1)-$(ARCH).tar && gzip -f builds/$(1)-$(ARCH).tar; fi
endef

define build_image
DOCKER_BUILDKIT=1 docker build $(DOCKER_BUILD_OPTION) -f docker/$(2) \
				--build-arg GS_MGMT_BUILDER_IMAGE=$(BUILDER) \
				--target $(1) -t $(call image_name,$(1)) .
$(call save,$(1))
endef

define build_agent_image
$(call build_image,$(1),agent.Dockerfile)
endef

TAI_META_CUSTOM_FILES ?= $(abspath $(wildcard scripts/tai/*))
TRANSPONDER_YANG ?= ./yang/goldstone-transponder.yang

all: builder images tester host-packages

images: south-images north-images xlate-images

GS_SOUTH_AGENTS ?= south-sonic south-tai south-onlp south-system south-gearbox south-dpll south-netlink
GS_NORTH_AGENTS ?= north-cli north-snmp north-netconf north-notif north-gnmi
GS_XLATE_AGENTS ?= xlate-oc

south-images: $(GS_SOUTH_AGENTS)

north-images: $(GS_NORTH_AGENTS)

xlate-images: $(GS_XLATE_AGENTS)

$(GS_SOUTH_AGENTS) $(GS_NORTH_AGENTS) $(GS_XLATE_AGENTS):
	$(call build_agent_image,$@)

north-snmp: snmpd

snmpd:
	$(call build_image,$@,snmpd.Dockerfile)

tester:
	$(call build_image,$@,builder.Dockerfile)

rust-tester:
	$(call build_image,$@,builder.Dockerfile)

builder:
	$(call build_image,$@,builder.Dockerfile)

host-packages:
	$(call build_image,$@,builder.Dockerfile)

yang:
	./tools/tai_yang_gen.py ./sm/oopt-tai/inc/tai.h $(TAI_META_CUSTOM_FILES) | pyang -f yang > $(TRANSPONDER_YANG)

bash:
	DOCKER_RUN_OPTION='-it --cap-add IPC_OWNER --cap-add IPC_LOCK' $(MAKE) cmd

rust:
	DOCKER_IMAGE=$(call image_name,rust-tester) DOCKER_RUN_OPTION='-it -v /var/lib/sysrepo:/var/lib/sysrepo -v /dev/shm:/dev/shm --privileged' $(MAKE) cmd

python:
	DOCKER_IMAGE=$(call image_name,tester) DOCKER_RUN_OPTION='-it -v /var/lib/sysrepo:/var/lib/sysrepo -v /dev/shm:/dev/shm --privileged' $(MAKE) cmd

tester-bash:
	DOCKER_RUN_OPTION='-it' DOCKER_IMAGE=$(call image_name,tester) $(MAKE) cmd

cmd:
	docker run $(DOCKER_RUN_OPTION) -v `pwd`:/data -w /data -v /etc/onl/platform:/etc/onl/platform $(DOCKER_IMAGE) $(DOCKER_CMD)

lint:
	which black && exit `black -q --diff --exclude src/north/snmp/src src | wc -l`
	which black && exit `black -q --diff --exclude "src/north/snmp/src|src/north/gnmi/goldstone/north/gnmi/proto" src | wc -l`
	TRANSPONDER_YANG=/tmp/test.yang $(MAKE) yang && diff /tmp/test.yang $(TRANSPONDER_YANG)
	scripts/gs-yang.py --lint south-sonic south-onlp south-tai south-system xlate-oc --search-dirs yang sm/openconfig
	scripts/gs-yang.py --lint south-gearbox south-onlp south-tai south-system xlate-oc --search-dirs yang sm/openconfig
	grep -rnI 'print(' src || exit 0 && exit 1

unittest: unittest-lib unittest-cli unittest-gearbox unittest-dpll unittest-openconfig unittest-tai unittest-sonic unittest-gnmi

rust-unittest: unittest-netlink

clean-sysrepo:
	rm -rf /dev/shm/sr* /var/lib/sysrepo

unittest-lib:
	$(MAKE) clean-sysrepo
	sysrepoctl --search-dirs yang --install yang/goldstone-interfaces.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-transponder.yang
	cd src/lib && python -m unittest -v -f $(TEST_CASE)

unittest-cli:
	$(MAKE) clean-sysrepo
	sysrepoctl --search-dirs yang --install yang/goldstone-interfaces.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-synce.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-static-macsec.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-vlan.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-uplink-failure-detection.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-portchannel.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-transponder.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-system.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-aaa.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-mgmt-interfaces.yang
	sysrepoctl --search-dirs yang --install yang/goldstone-ipv4.yang
	cd src/north/cli        && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)

unittest-gearbox:
	$(MAKE) clean-sysrepo
	scripts/gs-yang.py --install south-gearbox --search-dirs yang
	cd src/south/gearbox    && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)

unittest-dpll:
	$(MAKE) clean-sysrepo
	scripts/gs-yang.py --install south-dpll --search-dirs yang
	cd src/south/dpll && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)

unittest-openconfig:
	$(MAKE) clean-sysrepo
	scripts/gs-yang.py --install xlate-oc south-onlp south-tai south-gearbox south-system --search-dirs yang sm/openconfig
	cd src/xlate/openconfig && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)

unittest-tai:
	$(MAKE) clean-sysrepo
	scripts/gs-yang.py --install south-tai --search-dirs yang
	cd src/south/tai        && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)

unittest-sonic:
	$(MAKE) clean-sysrepo
	cd src/south/sonic && make proto
	scripts/gs-yang.py --install south-sonic --search-dirs yang
	cd src/south/sonic      && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)
	cd src/south/sonic      && make clean

unittest-netlink:
	$(MAKE) clean-sysrepo
	scripts/gs-yang.py --install south-netlink --search-dirs yang
	cd src/south/netlink && cargo test -- --nocapture

unittest-gnmi:
	$(MAKE) clean-sysrepo
	cd src/north/gnmi && make proto
	scripts/gs-yang.py --install xlate-oc --search-dirs yang sm/openconfig
	cd src/north/gnmi && PYTHONPATH=../../lib python -m unittest -v -f $(TEST_CASE)
	cd src/north/gnmi && make clean