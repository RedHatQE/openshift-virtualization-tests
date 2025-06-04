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

The tests can dynamically select test images based on the system's architecture. This is controlled by the environment variable `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH`. Supported architectures include:

- `x86_64` (default)

### Usage
The architecture-specific test images class is selected automatically based on the `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH` environment variable. If the variable is not set, the default architecture `x86_64` is used.

Ensure the environment variable is set correctly before running the tests:

```bash
export OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH=<desired-architecture>
```

If an unsupported architecture is specified, a `ValueError` will be raised.

Images for different architectures are managed under [utilities/constants.py](../utilities/constants.py) - `ArchImages`


## Python and dependencies
python >=3.12

The Complete list of environment dependencies can be found in [Dockerfile](../Dockerfile)


## virtctl

`virtctl` binary should be downloaded from `consoleCliDownloads` resource of the cluster under test.

## oc

`oc` client should be downloaded from `consoleCliDownloads` resource of the cluster under test.
