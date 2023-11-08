Goldstone Management Layer Implementation
---

`goldstone-mgmt` is the management layer implementation of Goldstone NOS.
The components in this repo are pre-installed in Goldstone NOS.

### What this repo includes

- Goldstone management north daemons that provide control interfaces to network operators (Blue boxes in the following diagram)
    - CLI, NETCONF, and SNMP
- Goldstone management south daemons that control hardware components in a networking device (Yellow boxes in the following diagram)
    - e.g) Switch ASIC, Transponder, Gearbox, Peripheral devices(Thermal sensors, LED, fan etc..)
- Goldstone management translation daemons that translate standarized YANG models and Goldstone YANG models (Red boxes in the following diagram)
    - OpenConfig Translator
- Goldstone management system daemons that provide service to north daemons by only interacting with south or xlate daemons
    - Streaming telemetry Server
- Goldstone YANG models
    - The schemas that are used between north and south daemons

![Goldstone Management Components](https://user-images.githubusercontent.com/5915117/173267760-44f93599-b6b0-4fd2-95e1-71cf8c07aed7.png)

### Getting Started

You can try running `goldstone-mgmt` components without a real networking device.
You need to set up a Kubernetes cluster for that. You can use [k3s](https://k3s.io/) to set it up quickly.

After making sure you have access to a Kubernetes cluster, try following.

```bash
$ git clone https://github.com/oopt-goldstone/goldstone-mgmt.git
$ cd goldstone-mgmt
$ kubectl apply -f k8s
$ kubectl get daemonset
NAME                  DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
south-sonic           1         1         1       1            1           <none>          70m
svclb-north-snmp      1         1         1       1            1           <none>          14m
svclb-north-netconf   1         1         1       1            1           <none>          14m
north-snmp            1         1         1       1            1           <none>          14m
north-netconf         1         1         1       1            1           <none>          14m
north-cli             1         1         1       1            1           <none>          14m
xlate-oc              1         1         1       1            1           <none>          14m
south-tai             1         1         1       1            1           <none>          14m
north-notif           1         1         1       1            1           <none>          14m
south-onlp            1         1         1       1            1           <none>          14m
south-system          1         1         1       1            1           <none>          14m
```

You can start the Goldstone CLI (`gscli`) by the following command

```bash
$ kubectl exec -it ds/north-cli -- gscli
> show version
latest
> show transponder summary
+-------------+-------------+--------------------+----------------------+--------------+-------------+
| transponder | vendor-name | vendor-part-number | vendor-serial-number | admin-status | oper-status |
+-------------+-------------+--------------------+----------------------+--------------+-------------+
| piu1        | BASIC       | N/A                | N/A                  |     down     | initialize  |
| piu2        | BASIC       | N/A                | N/A                  |     down     | initialize  |
| piu3        | N/A         | N/A                | N/A                  |     N/A      |     N/A     |
| piu4        | N/A         | N/A                | N/A                  |     N/A      |     N/A     |
| piu5        | N/A         | N/A                | N/A                  |     N/A      |     N/A     |
| piu6        | N/A         | N/A                | N/A                  |     N/A      |     N/A     |
+-------------+-------------+--------------------+----------------------+--------------+-------------+
> show chassis-hardware piu table
name    status     PIU type    CFP2 presence
------  ---------  ----------  ---------------
piu1    present    ACO         present
piu2    present    DCO         present
piu3    present    QSFP28      unplugged
piu4    unplugged  UNKNOWN     unplugged
piu5    present    ACO         unplugged
piu6    present    DCO         unplugged
```

### Architecture

The management layer of Goldstone needs to meet the following requirements.

- provide CLI, NETCONF, SNMP and gNMI services to operator
- support controlling various software that controls hardware components in a networking device
    - e.g) how to retrieve network interface information may vary among platforms

`goldstone-mgmt` uses [sysrepo](https://github.com/sysrepo/sysrepo) as a central configuration infrastructure.
`goldstone-mgmt` has its own native YANG models which are placed under [`yang/`](https://github.com/oopt-goldstone/goldstone-mgmt/tree/master/yang) directory.
The intention to have native YANG models is to fully cover what the underneath hardware supports.

Using the standard YANG models ([OpenConfig](https://www.openconfig.net/), [OpenROADM](http://openroadm.org/) etc..) is also supported by using translater daemons.

`goldstone-mgmt` framework has four kinds of daemon which interact with sysrepo datastore.

- north daemon
    - provides northbound API (CLI, NETCONF, SNMP, RESTCONF, gNMI etc..)
    - source code under [`src/north`](https://github.com/oopt-goldstone/goldstone-mgmt/tree/master/src/north)
- south daemon
    - control/monitor hardware (ONLP, SONiC/SAI, TAI, System)
    - uses native YANG models to interact with sysrepo
    - source code under [`src/south`](https://github.com/oopt-goldstone/goldstone-mgmt/tree/master/src/south)
- translation daemon
    - translator of the standarized YANG models and Goldstone YANG models
    - source code under [`src/xlate`](https://github.com/oopt-goldstone/goldstone-mgmt/tree/master/src/xlate)
- system daemon
    - provides system utility services for north daemons
    - optionally uses native YANG models to interact with sysrepo
    - source code under [`src/system`](https://github.com/oopt-goldstone/goldstone-mgmt/tree/master/src/system)

### How to build

#### Prerequisite

- Git
- Docker ( version >= 18.09, enable [buildkit](https://docs.docker.com/develop/develop-images/build_enhancements/) )

```bash
$ git clone https://github.com/oopt-goldstone/goldstone-mgmt.git
$ cd goldstone-mgmt
$ git submodule update --init
$ make all
```

This will build all Goldstone management components as container images.

```bash
$ docker images | grep oopt-goldstone/mgmt
ghcr.io/oopt-goldstone/mgmt/south-onlp      latest           3306a75b5445   3 hours ago     228MB
ghcr.io/oopt-goldstone/mgmt/builder         latest           50b26971c311   3 hours ago     1.67GB
ghcr.io/oopt-goldstone/mgmt/south-tai       latest           6cb422fe2d4c   3 hours ago     228MB
ghcr.io/oopt-goldstone/mgmt/south-gearbox   latest           663bb2dc39aa   3 hours ago     227MB
ghcr.io/oopt-goldstone/mgmt/north-notif     latest           6407dee38cc6   3 hours ago     210MB
ghcr.io/oopt-goldstone/mgmt/north-snmp      latest           062ad6d39b28   3 hours ago     200MB
ghcr.io/oopt-goldstone/mgmt/south-sonic     latest           c5156742195b   3 hours ago     281MB
ghcr.io/oopt-goldstone/mgmt/north-netconf   latest           78ff4effe763   3 hours ago     476MB
ghcr.io/oopt-goldstone/mgmt/south-system    latest           fa83287947bd   3 hours ago     252MB
ghcr.io/oopt-goldstone/mgmt/north-cli       latest           fe8286bf95fb   3 hours ago     238MB
ghcr.io/oopt-goldstone/mgmt/xlate-oc        latest           79e3e935785a   3 hours ago     211MB
ghcr.io/oopt-goldstone/mgmt/snmpd           latest           eca87e95b7a4   3 hours ago     174MB
```
