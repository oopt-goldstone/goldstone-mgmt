Goldstone Management Layer Implementation
---

`goldstone-mgmt` is the management layer implementation of Goldstone NOS.
The components in this repo are pre-installed in Goldstone NOS.

### What this repo includes

- Goldstone management north daemons that provide control interfaces to network operators
    - CLI, NETCONF, and SNMP
- Goldstone management south daemons that control hardware components in a networking device
    - e.g) Switch ASIC, Transponder, Gearbox, Peripheral devices(Thermal sensors, LED, fan etc..)
- Goldstone YANG models
    - The schemas that are used between north and south daemons

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
`goldstone-mgmt` has its own native YANG models which are placed under `yang/` directory.
The intention to have native YANG models is to fully cover what the underneath hardware supports.

Using the standard YANG models (OpenConfig, OpenROADM etc..) is also supported by using translater daemons.

`goldstone-mgmt` framework has three kinds of daemon which interact with sysrepo datastore.

- north daemon
    - provides northbound API (CLI, NETCONF, SNMP, RESTCONF, gNMI etc..)
    - source code under `src/north`
- south daemon
    - control/monitor hardware (ONLP, SONiC/SAI, TAI, System)
    - uses native YANG models to interact with sysrepo
    - source code under `src/south`
- translater daemon
    - translater of the native YANG models and standard YANG models
    - source code under `src/xlate`

### How to build

#### Prerequisite

- Git
- Docker ( version >= 18.09, enable [buildkit](https://docs.docker.com/develop/develop-images/build_enhancements/) )

```bash
$ git clone https://github.com/oopt-goldstone/goldstone-mgmt.git
$ cd goldstone-mgmt
$ git submodule --update --init
$ make all
```
