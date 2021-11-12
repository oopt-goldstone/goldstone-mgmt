Goldstone Management Framework
---

### What this repo inclues

- Goldstone management south daemons
    - ONLP, SONiC/SAI, TAI, System
- Goldstone management north daemons
    - CLI, netconf(Netopeer2), SNMP
- Goldstone YANG models

### Architecture

`goldstone-mgmt` is the management layer implementation of OOPT Goldstone.

The management layer of Goldstone needs to meet the following requirements.

- provide CLI, NETCONF, SNMP and gNMI services to operator
- support controlling various software that controls hardware components in the networking device
    - e.g) how to retrieve the interface information may vary among platforms

In order to meet these requirements, the management layer needs a modular


framework uses [sysrepo](https://github.com/sysrepo/sysrepo) as a central configuration
infrastructure. sysrepo is a YANG based configuration datastore. Since it uses POSIX shared memory for
the temporal storage, it works without a daemon which needs to be running all the time.
Exclusive control among processes is done by FUTEX and persistent data (e.g. startup config or YANG model)
is just ordinal files. (access control is also enforced by UNIX file permissions)

`goldstone-mgmt` has its own native YANG models which are placed under `yang/` directory.
The intention to have native YANG models is to properly cover what the underneath hardware supports.

Using the standard YANG models (OpenConfig, IETF etc..) is also supported by using translater daemons which will be described below.

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

#### South Daemon

South daemon is an entity which acts as a gateway between sysrepo datastore 
and hardware controller of the platform. We plan to have ONLP, SONiC and TAI south daemon for now.

##### 1. ONLP south daemon

[ONLP](http://opencomputeproject.github.io/OpenNetworkLinux/onlp/) south daemon is a south daemon which handles peripheral control of the platform.
It controls the peripherals via the ONLP Python wrapper.

##### 2. SONiC/SAI south daemon

SONiC/SAI south daemon is a south daemon which handles Ethernet ASIC control of the platform.
It controls the ASIC via [sonic-py-swsssdk](https://github.com/Azure/sonic-py-swsssdk) library.

##### 3. TAI south daemon

TAI south daemon is a south daemon which handles coherent optics control of the platform.
It controls the optical modules via [taish gRPC API](https://github.com/Telecominfraproject/oopt-tai/tree/master/tools/taish).

#### North Daemon

North daemon is an entity which provides northband interface to the user.
We plan to implement CLI, NETCONF and SNMP north daemon first.

##### 1. CLI north daemon

- supports basic set/get, completion and notification
- python-prompt-toolkit based
    - https://github.com/prompt-toolkit/python-prompt-toolkit
    - many users, active development
    - performance could be a problem when syntax tree get larger
    - needs to develop Python wrapper for sysrepo(devel)?
- TODO: consider automatic code generation based on YANG models

##### 2. NETCONF north daemon

- we use [Netopeer2](https://github.com/CESNET/Netopeer2) as is

##### 3. SNMP north daemon

- candidate libraries to use
    - https://github.com/Azure/sonic-snmpagent
    - https://github.com/etingof/pysnmp
    - net-snmp
        - https://github.com/opencomputeproject/OpenNetworkLinux/tree/master/packages/base/any/onlp-snmpd/builds/src/onlp_snmp

### How to test

#### prerequisite

- Git
- Docker ( version >= 18.09, enable [buildkit](https://docs.docker.com/develop/develop-images/build_enhancements/) )

```bash
$ git clone git@github.com:oopt-goldstone/goldstone-mgmt.git
$ cd goldstone-mgmt
$ git submodule --update --init
$ make all
$ kubectl apply -f k8s
```
