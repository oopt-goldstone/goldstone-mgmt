Goldstone Management Framework
---

### What this repo could have

- south daemons
    - ONLP, SONiC/SAI, TAI
- north daemons
    - CLI, netconf(Netopeer2), SNMP
- Goldstone YANG model

### Architecture

`goldstone-mgmt` framework uses [sysrepo](https://github.com/sysrepo/sysrepo) as a central configuration
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
    - control/monitor hardware (ONLP, SONiC/SAI, TAI)
    - uses native YANG models to interact with sysrepo
    - source code under `src/south`
- translater daemon
    - translater of the native YANG models and standard YANG models
    - source code under `src/xlate`

#### South Daemon

South daemon is an entity which acts as a gateway between sysrepo datastore 
and hardware controller of the platform. We plan to have ONLP, SONiC and TAI south daemon for now.

##### 1. ONLP south daemon (C++)

[ONLP](http://opencomputeproject.github.io/OpenNetworkLinux/onlp/) south daemon is a south daemon which handles peripheral control of the platform.
It controls the peripherals via `libonlp.so`. 

##### 2. SONiC/SAI south daemon (C++)

SONiC/SAI south daemon is a south daemon which handles Ethernet ASIC control of the platform.
It controls the ASIC via [sonic-swss-common](https://github.com/Azure/sonic-swss-common) library.

##### 3. TAI south daemon (C++)

TAI south daemon is a south daemon which handles coherent optics control of the platform.
It controls the optical modules via [taish gRPC API](https://github.com/Telecominfraproject/oopt-tai/tree/master/tools/taish).

#### North Daemon

North daemon is an entity which provides northband interface to the user.
We plan to implement CLI, NETCONF and SNMP north daemon first.

##### 1. CLI north daemon (Python)

- supports basic set/get, completion and notification
- python-prompt-toolkit based
    - https://github.com/prompt-toolkit/python-prompt-toolkit
    - many users, active development
    - performance could be a problem when syntax tree get larger
    - needs to develop Python wrapper for sysrepo(devel)?
- TODO: consider automatic code generation based on YANG models
- alternatives
    - klish

##### 2. NETCONF north daemon

- we can use [Netopeer2](https://github.com/CESNET/Netopeer2) as is (hopefully)

##### 3. SNMP north daemon

- candidate libraries to use
    - https://github.com/Azure/sonic-snmpagent
    - https://github.com/etingof/pysnmp
    - net-snmp
        - https://github.com/opencomputeproject/OpenNetworkLinux/tree/master/packages/base/any/onlp-snmpd/builds/src/onlp_snmp

### How to test

```bash
$ git clone git@github.com:ishidawataru/goldstone-mgmt.git
$ git submodule --update --init --recursive
$ make docker-image
$ make bash
# make south
# make init
# ./src/south/onlp/main

---

$ # from a different terminal
$ docker exec -it sysrepo bash
# ./src/south/openconfig-converter/main

---

$ # from another terminal
$ docker exec -it sysrepo bash
root@d67dc2076ab2:/data# sysrepocfg -d operational -f json -X --xpath "/goldstone-onlp:components/component[name='thermal0']"
{
  "goldstone-onlp:components": {
    "component": [
      {
        "name": "thermal0",
        "config": {
          "name": "thermal0"
        },
        "fan": {

        },
        "thermal": {
          "state": {
            "thresholds": {
              "warning": 45000,
              "error": 55000,
              "shutdown": 60000
            },
            "capability": [
              "GET_TEMPERATURE",
              "GET_WARNING_THRESHOLD",
              "GET_ERROR_THRESHOLD",
              "GET_SHUTDOWN_THRESHOLD"
            ],
            "temperature": 38000,
            "status": [
              "PRESENT"
            ]
          }
        },
        "led": {

        },
        "sys": {

        },
        "psu": {

        },
        "state": {
          "id": 33554433,
          "description": "CPU Core",
          "type": "THERMAL"
        }
      }
    ]
  }
}
root@d67dc2076ab2:/data# sysrepocfg -d operational -f json -X --xpath "/openconfig-platform:components/component[name='thermal0']"
{
  "openconfig-platform:components": {
    "component": [
      {
        "name": "thermal0",
        "state": {
          "description": "CPU Core",
          "id": "0x2000001",
          "temperature": {
            "instant": "38.0"
          },
          "empty": false
        },
        "chassis": {

        },
        "port": {

        },
        "power-supply": {
          "state": {
            "openconfig-platform-psu:enabled": true
          }
        },
        "fan": {

        },
        "fabric": {

        },
        "storage": {

        },
        "cpu": {

        },
        "integrated-circuit": {

        },
        "backplane": {

        }
      }
    ]
  }
}
```

