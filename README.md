Goldstone Management Framework
---

### What this repo could have

- south daemons
    - ONLP, SONiC/SAI, TAI
- north daemons
    - CLI, netconf(Netopeer2), SNMP
- Goldstone YANG model

### north CLI

- should support basic set/get, completion and notification
- python-prompt-toolkit based?
    - https://github.com/prompt-toolkit/python-prompt-toolkit
    - many users, active development
    - performance could be a problem when syntax tree get larger
    - needs to develop Python wrapper for sysrepo(devel)?

### How to test

```bash
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

