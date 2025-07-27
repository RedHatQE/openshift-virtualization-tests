# Getting started
## Installation

Install [uv](https://github.com/astral-sh/uv)

To update one package:
```bash
uv lock --upgrade-package openshift-python-wrapper
```

To update all the packages
```bash
uv lock --upgrade
```

## Prerequisites

### Cluster requirements
This project runs tests on an OpenShift cluster with Openshift Virtualization (CNV) installed.
Some tests may require additional StorageClasses to be deployed.

When running Windows tests, the cluster should have at least 16GiB RAM and 80G volume size.

You can log in into such a cluster via:

```bash
oc login -u user -p password
```

Or by setting `KUBECONFIG` variable:

```bash
export KUBECONFIG=<kubeconfig file>
```

or by saving the kubeconfig file under `~/.kube/config`


## Test Images Architecture Support

The tests can dynamically select test images based on the system's architecture.
Please refer to [ARCHITECTURE_SUPPORT.md](ARCHITECTURE_SUPPORT.md) for more details.


## Python and dependencies
python >=3.12

The Complete list of environment dependencies can be found in [Dockerfile](../Dockerfile)


## virtctl

`virtctl` binary should be downloaded from `consoleCliDownloads` resource of the cluster under test.

## oc

`oc` client should be downloaded from `consoleCliDownloads` resource of the cluster under test.
