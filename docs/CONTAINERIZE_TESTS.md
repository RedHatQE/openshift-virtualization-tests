# Building and pushing openshift-virtualization-tests container image

## Building and pushing openshift-virtualization-tests container image

Container can be generated and pushed using make targets.

```
make build-container
make push-container
```

### optional parameters

```
export IMAGE_BUILD_CMD=<docker/podman>               # default "docker"
export IMAGE_REGISTRY=<container image registry>     # default "quay.io"
export REGISTRY_NAMESPACE=<your quay.io namespace>   # default "openshift-cnv"
export OPERATOR_IMAGE_NAME=<image name>              # default "openshift-virtualization-tests"
export IMAGE_TAG=<the image tag to use>              # default "latest"
```

You can build the image with specific commit hashes for openshift-python-wrapper, openshift-python-utilities and timeout-sampler.
The following args are supported:

```
OPENSHIFT_PYTHON_WRAPPER_COMMIT
OPENSHIFT_PYTHON_UTILITIES_COMMIT
TIMEOUT_SAMPLER_COMMIT
```

### Running containerized tests locally
Save kubeconfig file to a local directory, for example: `$HOME/kubeconfig`

### Running containerized tests examples

For running tests, you need to have access to artifactory server with images.
Environment variables `ARTIFACTORY_USER` and `ARTIFACTORY_TOKEN` expected to be set up for local runs.

```bash
podman run -v "$(pwd)"/toContainer:/mnt/host:Z -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests
```

To overwrite the default image server, set the `HTTP_IMAGE_SERVER` environment variable:

```bash
podman run -v "$(pwd)"/toContainer:/mnt/host:Z -e KUBECONFIG=/mnt/host/kubeconfig -e HTTP_IMAGE_SERVER="X.X.X.X" quay.io/openshift-cnv/openshift-virtualization-tests

```


#### Smoke tests

```
podman run -v "$(pwd)"/toContainer:/mnt/host:Z -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests \
uv run pytest --storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization --default-storage-class=ocs-storagecluster-ceph-rbd-virtualization \
--tc default_volume_mode:Block --latest-rhel -m smoke
```

#### IBM cloud Win10 tests

```
podman run -v "$(pwd)"/toContainer:/mnt/host:Z -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests \
uv run pytest --tc=server_url:"X.X.X.X" --windows-os-matrix=win-10 --storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization -m ibm_bare_metal
```
