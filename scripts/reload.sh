#!/bin/bash

set -eux

rm -rf /var/lib/sysrepo/* /dev/shm/sr_*

sysrepoctl -s/var/lib/goldstone/yang/gs --install /var/lib/goldstone/yang/gs/goldstone-tai.yang,/var/lib/goldstone/yang/gs/goldstone-onlp.yang
sysrepoctl -s/var/lib/goldstone/yang/gs --install /var/lib/goldstone/yang/gs/goldstone-interfaces.yang,/var/lib/goldstone/yang/gs/goldstone-mgmt-interfaces.yang,/var/lib/goldstone/yang/gs/goldstone-ip.yang,/var/lib/goldstone/yang/gs/goldstone-arp.yang,/var/lib/goldstone/yang/gs/goldstone-portchannel.yang,/var/lib/goldstone/yang/gs/goldstone-vlan.yang,/var/lib/goldstone/yang/gs/goldstone-aaa.yang
