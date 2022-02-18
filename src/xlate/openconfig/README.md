# OpenConfig Translator

The OpenConfig translator is a translator daemon which translates between OpenConfig models and Goldstone native/primitive models. It allows north daemons to control and manage the device with OpenConfig models.

## Supported OpenConfig models and revisions

OpenConfig translator partially supports following models:

- openconfig-interfaces 2021-04-06
- openconfig-if-ethernet 2021-07-07
- openconfig-platform 2021-01-18
- openconfig-platform-types 2021-01-18
- openconfig-platform-port 2021-06-16
- openconfig-platform-transceiver 2021-02-23
- openconfig-platform-fan 2018-11-21
- openconfig-platform-psu 2018-11-21
- openconfig-terminal-device 2021-02-23
- openconfig-transport-line-common 2019-06-03
- openconfig-transport-types 2021-03-22
- openconfig-types 2019-04-16
- openconfig-yang-types 2021-03-02

## Prerequisites

- Python >= 3.8
- Goldstone patched sysrepo-python
- Goldstone patched libyang-python

Other required python packages are listed in `requirements.txt`.

### Required Goldstone native/primitive models

- goldstone-component-connection 2021-11-01
- goldstone-gearbox 2021-10-08
- goldstone-interfaces 2020-10-13
- goldstone-platform 2019-11-01
- goldstone-system 2020-11-23
- goldstone-transponder 2019-11-01

## Install

```sh
sudo pip3 install .
```

## Usage

```sh
$ gsxlated-openconfig -h
usage: gsxlated-openconfig [-h] [-v] operational-modes-file

positional arguments:
  operational-modes-file
                        path to operational-modes config file

options:
  -h, --help            show this help message and exit
  -v, --verbose         enable detailed output
```

Example:

```sh
gsxlated-openconfig operational-modes.json
```
