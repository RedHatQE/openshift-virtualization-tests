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
This project runs tests against an OpenShift cluster with CNV installed.
Some tests may require additional StorageClasses to be deployed.

When running Windows tests, the cluster should have at least 16GiB RAM (XL deployment)
and 80G volume size (default deployment configuration).

You can log in into such a cluster via:

```bash
oc login -u user -p password
```

Or by setting `KUBECONFIG` variable:

```bash
KUBECONFIG=<kubeconfig file>
```

or by saving the kubeconfig file under `~/.kube/config`

### Kubevirtci Kubernetes provider

When you want to run the test on k8s (and not okd/ocp) provider, you need to make sure that the
cluster can reach the outside world to fetch docker images. Usually all that is required is adding the
following like to your system `/etc/resolv.conf`:

```
nameserver 192.168.8.1
```


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

Images for different architectures are managed under [utilities/constants.py](utilities/constants.py) - `ArchImages`

## Using custom cluster management binaries

If you need to use custom or system `kubectl`, `virtctl` or `oc` instead of wrappers from `local-cluster`,
define `KUBECTL`, `CNV_TESTS_VIRTCTL_BIN` and `CNV_TESTS_OC_BIN` environment variables to point to the binaries.

## Python and dependencies
python >=3.12

The following binaries are needed:

```bash
sudo dnf install python3-devel  \
                 libcurl-devel  \
                 libxml-devel   \
                 openssl-devel  \
                 libxslt-devel  \
                 libxml++-devel \
                 libxml2-devel
```

## virtctl

`virtctl` binary should be downloaded from `consoleCliDownloads` resource of the cluster under test.

## oc

`oc` client should be downloaded from `consoleCliDownloads` resource of the cluster under test.
