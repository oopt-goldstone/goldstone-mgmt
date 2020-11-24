#!/bin/bash

set -eux

rm -rf /var/lib/sysrepo/* /dev/shm/sr_*

for model in $(ls /var/lib/goldstone/yang/gs);
do
    sysrepoctl -s/var/lib/goldstone/yang/gs --install /var/lib/goldstone/yang/gs/${model}
    sysrepoctl -c $(echo $model | cut -d '.' -f 1) -p 666
done
