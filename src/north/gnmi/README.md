# gNMI Server

The gNMI server is a north layer daemon which provides gNMI service as a southbound interface for SDN controllers.

## Capabilities

The gNMI server intends to implement [gRPC Network Management Interface (gNMI)](https://github.com/openconfig/reference/blob/master/rpc/gnmi/gnmi-specification.md) specification version 0.6.0.

The gNMI server supports following gNMI RPCs:

- `Capabilities`
- `Get`
- `Set`

The gNMI server supports limited `Set` transaction. It has following limitations:

- If a same path requested multiple times in a transaction, it will be failed.
- Operational states may appear to be changed during a transaction.

Currently, the gNMI server does not yet support following features:

- `Subscribe` RPC
- `replace` operation for `Set` RPC
- `type` specification for `Get` RPC
- Wildcards in a `path` field
- Value encodings other than JSON
- RPC on TLS
- RPC authentication and authorization

## Prerequisites

- Python >= 3.8
- Goldstone patched sysrepo-python
- Goldstone patched libyang-python

Other required python packages are listed in `requirements.txt`.

Additional required python packages for developers are listed in `requirements_dev.txt`.

## Install

```sh
make proto
sudo pip3 install .
```

## Usage

```sh
$ gsnorthd-gnmi -h
usage: gsnorthd-gnmi [-h] [-v] [-p SECURE_PORT] [-i INSECURE_PORT] supported_models_file

positional arguments:
  supported_models_file
                        path to a JSON file which is listed yang models supported by the gNMI server

options:
  -h, --help            show this help message and exit
  -v, --verbose
  -p SECURE_PORT, --secure-port SECURE_PORT
  -i INSECURE_PORT, --insecure-port INSECURE_PORT
```

Example:

```sh
gsnorthd-gnmi gnmi-supported-models.json
```
