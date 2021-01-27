#!/bin/bash

set -eux

rm -rf /var/lib/sysrepo/* /dev/shm/sr_*

for model in $(ls $GS_YANG_REPO);
do
    sysrepoctl -s${GS_YANG_REPO} --install ${GS_YANG_REPO}/${model}
    sysrepoctl -c $(echo $model | cut -d '.' -f 1) -p 666
done

sysrepoctl -s ${OC_YANG_REPO}:${IETF_YANG_REPO} --install ${IETF_YANG_REPO}/iana-if-type.yang
sysrepoctl -s ${OC_YANG_REPO}:${IETF_YANG_REPO} --install ${OC_YANG_REPO}/interfaces/openconfig-interfaces.yang
