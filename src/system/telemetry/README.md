# Streaming Telemetry Server

The streaming telemetry server provides `goldstone-telemetry` service. It allows north daemons to subscribe configuration/operational state changes of the device.

## Supported models and revisions

- goldstone-telemetry 2022-05-25

## Prerequisites

- Python >= 3.8
- Goldstone patched sysrepo-python
- Goldstone patched libyang-python

Other required python packages are listed in `requirements.txt`.

## Install

```sh
sudo pip3 install .
```

## Usage

```sh
$ gssystemd-telemetry -h
usage: gssystemd-telemetry [-h] [-v]

options:
  -h, --help            show this help message and exit
  -v, --verbose         enable detailed output
```

Example:

```sh
gssystemd-telemetry
```
