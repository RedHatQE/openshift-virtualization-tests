# Building and pushing openshift-virtualization-tests container image

If your cluster does not have access to internal RedHat network - you may build openshift-virtualization-tests
container and run it directly on a cluster.

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

### Running containerized tests locally
Save kubeconfig file to a local directory, for example: `$HOME/kubeconfig`
To run tests in containerized environment:

```bash
podman run  -v $HOME:/mnt/host:Z  -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests
```

### Running containerized tests examples

For running tests, you need to have access to artifactory server with images.
Environment variables `ARTIFACTORY_USER` and `ARTIFACTORY_TOKEN` expected to be set up for local runs.

Also need to create the folder which should contain `kubeconfig`, binaries `oc`, `virtctl` and **ssh key** for access
to nodes. This folder should be mounted to container during the run.

#### Running a default set of tests

```
docker run -v "$(pwd)"/toContainer:/mnt/host:Z -e -e KUBECONFIG=/mnt/host/kubeconfig -e HTTP_IMAGE_SERVER="X.X.X.X" quay.io/openshift-cnv/openshift-virtualization-tests
```

#### Smoke tests

```
docker run -v "$(pwd)"/toContainer:/mnt/host:Z -e -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests \
uv run pytest --tc=server_url:"X.X.X.X" --storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization --default-storage-class=ocs-storagecluster-ceph-rbd-virtualization -m smoke
```

#### IBM cloud Win10 tests

```
docker run -v "$(pwd)"/toContainer:/mnt/host:Z -e -e KUBECONFIG=/mnt/host/kubeconfig quay.io/openshift-cnv/openshift-virtualization-tests \
uv run pytest --tc=server_url:"X.X.X.X" --windows-os-matrix=win-10 --storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization --default-storage-class=ocs-storagecluster-ceph-rbd-virtualization -m ibm_bare_metal
```
