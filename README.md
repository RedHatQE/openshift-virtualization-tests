# openshift-virtualization-tests

This repository contains tests to verify the functionality of OpenShift with `OpenShift Virtualization`.

## Cluster requirements

When running Windows tests, the cluster should have at least 16GiB RAM (XL deployment)
and 80G volume size (default deployment configuration).

Upgrade tests must be run against a large deployment(24GiB RAM, 250GB volume size)
Upgrade network tests can't be run against a non-multi-nic cluster. To run upgrade against
such clusters, we must ignore network component
```bash
--ignore=tests/network/
```

## Prerequirements

python >=3.12

Following binaries are needed:

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

## Setup VirtualEnv

We use [uv](https://github.com/astral-sh/uv) to manage virtualenv.

To update one package:

```bash
uv lock --upgrade-package openshift-python-wrapper
```
To update all the packages
```bash
uv lock --upgrade
```

# Getting started

## Prepare CNV cluster

This project runs tests against a cluster with running CNV instance.

### Arbitrary cluster

These tests can be executed against arbitrary OpenShift cluster with CNV installed.

You can login into such cluster via:

```bash
oc login -u user -p password
```

Or by setting `KUBECONFIG` variable:

```bash
KUBECONFIG=<kubeconfig file>
```

### Kubevirtci Kubernetes provider

When you want to run the test on k8s (and not okd/ocp) provider, you need to make sure that the
cluster can reach outside world to fetch docker images. Usually all that is required is adding the
following like to your system `/etc/resolv.conf`:

```
nameserver 192.168.8.1
```

### Using custom cluster management binaries

If you need to use custom or system `kubectl`, `virtctl` or `oc` instead of wrappers from `local-cluster`,
define `KUBECTL`, `CNV_TESTS_VIRTCTL_BIN` and `CNV_TESTS_OC_BIN` environment variables to point to the binaries.

## Running the tests

## Running chaos tests

`chaos` tests disrupt the cluster in different ways in order to build confidence in the robustness of `OpenShift Virtualization`.

To run the chaos tests:

```bash
pytest <pytest_args> -m chaos
```

## Other parameters

### Logging

Log file 'pytest-tests.log' is generated with the full pytest output in openshift-virtualization-tests root directory.
For each test failure cluster logs are collected and stored under 'tests-collected-info'.

To see verbose logging of a test run, add the following parameter:

```bash
pytest <test_to_run> -o log_cli=true
```

openshift-virtualization-tests would collect must-gather data, pexpect logs, alert data for failure analysis, when --data-collector argument is passed.
Logs will be available under tests-collected-info/ folder for local runs and /data/tests-collected-info for containerized runs.

```bash
pytest <test_to_run> --data-collector
```

To skip must-gather collection on a given module or test, skip_must_gather_collection can be used:

```bash
pytest.mark.skip_must_gather_collection
```

### Selecting tests

To run a particular set of tests, you can use name pattern matching.
For example, to run all tests that contain `test_clone_windows_vm` or `test_migrate_vm` in their names:

```bash
pytest <pytest_args> -k "test_clone_windows_vm or test_migrate_vm"
```

To run all network component tests:

```bash
pytest <pytest_args> -m network
```

#### Selecting network IP version type tests

You can use marker matching to select tests based on their IP version type.
The available markers are: ipv4 and ipv6.
These markers are useful when running tests in an IPv4 or IPv6 single-stack cluster.

For example, to run only the IPV4 network tests:

```bash
uv run pytest -m "network and ipv4"
```

You can also run all IPV4 network tests in addition to all the other general
tests that are not specifically marked with IP version type marker:

```bash
uv run pytest -m "network and not ipv6"
```

## Install openshift-virtualization tests

Installation tests allow us to use either the `production` or `osbs` catalogsource for deployment.

Note:
1. Install test expects no cnv installation exists on the cluster. Installation of openshift-virtualization x.y._ is only supported on ocp x.y._
2. CNV_VERSION_EXPLORER_URL environment variable expected to be set up for local runs. URL information can be found in Confluence.

##### Install from production catalogsource

In this case, installation of openshift virtualization would take place using redhat-operator catalogsource.

```bash
pytest tests/install_upgrade_operators/product_install/test_install_openshift_virtualization.py --install --cnv-source production
```

##### Install from osbs catalogsource

In this case, installation would take place using a custom catalogsource using specified IIB image. Currently only installation using brew url is supported.

```bash
pytest tests/install_upgrade_operators/product_install/test_install_openshift_virtualization.py --install --cnv-source osbs --cnv-image brew.registry.redhat.io/rh-osbs/iib:<image>
```

## Upgrade tests

Current upgrade test automation allows us to run just the ocp/cnv/eus upgrade. <br />
As default, the upgrade will run with pre and post upgrade validation of various components.

Note:
1. Before running upgrade tests, please check "Cluster requirements" section to see minimum requirements in terms of cluster size.
2. CNV_VERSION_EXPLORER_URL environment variable expected to be set up for local runs. URL information can be found in Confluence.

##### Y-stream Upgrade

In this case, upgrade testing would always involve upgrading both ocp and cnv.
Please note, in Y-1 -> Y upgrade, OCP must be upgraded first, followed by CNV upgrades. (e.g. upgrading from 4.Y latest z stream -> 4.Y+1.0, ocp must be upgraded to 4.Y+1 first, before cnv can be upgraded).

##### Z-stream Upgrade

Here, no ocp upgrade is needed (e.g. 4.Y.z-1 -> 4.Y.z).

##### EUS Upgrade:
EUS-to-EUS updates are only viable between even-numbered minor versions of OpenShift Container Platform. (e.g 4.Y.z -> 4.Y+2.z)


#### OCP upgrade

Command to run entire upgrade test suite for ocp upgrade, including pre and post upgrade validation:

```bash
--upgrade ocp --ocp-image <ocp_image_to_upgrade_to>
```

Command to run only ocp upgrade test, without any pre/post validation:

```bash
-m ocp_upgrade --upgrade ocp --ocp-image <ocp_image_to_upgrade_to>
```

To upgrade to ocp version: 4.10.16, using <https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com/releasestream/4-stable/release/4.10.16>, following command can be used:

```bash
--upgrade ocp --ocp-image quay.io/openshift-release-dev/ocp-release:4.10.16-x86_64
```

Note: OCP images information can be found at: <https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com/>.

Currently, automation supports ocp upgrades using stable, ci, nightly and rc images for ocp

#### CNV upgrade

Command to run entire upgrade test suite for cnv upgrade, including pre and post upgrade validation:

```bash
--upgrade cnv --cnv-version <target_version> --cnv-source <osbs|production|staging> --cnv-image <cnv_image_to_upgrade_to>
```

Command to run only cnv upgrade test, without any pre/post validation:

```bash
-m cnv_upgrade --upgrade cnv --cnv-version <target_version> --cnv source <osbs|production|staging> --cnv-image <cnv_image_to_upgrade_to>
```

To upgrade to cnv 4.Y.z, using the cnv image that has been shipped, following command could be used:
```bash
--upgrade cnv --cnv-version 4.Y.z --cnv-source osbs --cnv-image <cnv_image_to_upgrade_to>
```

#### EUS upgrade
You must provide --eus-ocp-images via cli, which is two comma separated ocp images for EUS upgrade.
The default target cnv version will be 4.Y+2.0. Optionally, --eus-csv-target-version can be provided for 4.Y+2.z version.
Command to run entire upgrade test suite for EUS upgrade, including pre and post upgrade validation:

```bash
--upgrade eus --eus-ocp-images <ocp_image_version_4.y+1.z>,<ocp_image_version_4.y+2.z> --eus-cnv-target-version <4.Y+2.z|None>
```
#### Custom upgrade lanes

The argument `--upgrade_custom` can be used instead of `--upgrade` to run custom upgrade lanes with non-default configurations (e.g., with customized HCO feature gates).

Note: custom upgrades should not be combined, to exclude unnecessary components `--ignore` argument can be used (e.g. `--ignore=tests/compute/upgrade_custom/swap/`)

### Other parameters

There are other parameters that can be passed to the test suite if needed.

```bash
--tc-file=tests/global_config.py
--tc-format=python
--junitxml /tmp/xunit_results.xml
--jira
--jira-url=<url>
--jira-user=<username>
--jira-password=<password>
--jira-no-ssl-verify
--jira-disable-docs-search
```

### Using pytest_jira

pytest_jira plugin allows you to link tests to existing tickets.
To use the plugin during a test run, use '--jira'.
Issues are considered as resolved if their status appears in resolved_statuses (verified, release pending, closed),
that are set as an environment variable in openshift-virtualization-tests GitHub repository, and saved to the temporary file jira.cfg.
You can mark a test to be skipped if a Jira issue is not resolved.
Example:

```
@pytest.mark.jira("CNV-1234", run=False)
```

You can mark a test to be marked as xfail if a Jira issue is not resolved.
Example:

```
@pytest.mark.jira("CNV-1234")
```

### Running tests using matrix fixtures

Matrix fixtures can be added in global_config.py.
You can run a test using a subset of a simple matrix (i.e flat list), example:

```bash
--bridge-device-matrix=linux-bridge
```

To run a test using a subset of a complex matrix (e.g list of dicts), you'll also need to add
the following to `openshift-virtualization-tests/conftest.py`

- Add `parser.addoption` under `pytest_addoption` (the name must end with `_matrix`)

Multiple keys can be selected by passing them with `,`

Available storage classes can be found in `global_config.py` under `storage_class_matrix` dictionary.

Example:

```bash
--storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization
```
Two storage classes hostpath-csi-pvc-block and hostpath-csi-basic can be added to global config's storage_class_matrix, via command-line:
```bash
--storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization,hostpath-csi-basic,hostpath-csi-pvc-block
--storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization,hostpath-csi-basic
```

Note: hostpath-csi-pvc-block and hostpath-csi-basic are not expected to be deployed in the same cluster with lvms-vg1.

### Using matrix fixtures

Using matrix fixtures requires providing a scope.
Format:

```
<type>_matrix__<scope>__
```

Example:

```
storage_class_matrix__module__
storage_class_matrix__class__
```

### Using customized matrix fixtures

You can customize existing matrix with function logic.
For example, when tests need to run on storage matrix, but only on storage
with snapshot capabilities.

Add a desired function logic to `pytest_matrix_utils.py`

```
def foo_matrix(matrix):
    <customize matrix code>
    return matrix
```

Example:

```
storage_class_matrix_foo_matrix__module__
storage_class_matrix_foo_matrix__class__
```

### Custom global_config to override the matrix value

To override the matrix value, you can create your own `global_config` file and pass the necessary parameters.

Example for AWS cluster:

`--tc-file=tests/global_config_aws.py --storage-class-matrix=px-csi-db-shared`

Example for SNO cluster:

`--tc-file=tests/global_config_sno.py --storage-class-matrix=lvms-vg1`

### Setting log level in command line

In order to run a test with a log level that is different from the default,
use the --log-cli-level command line switch.
The full list of possible log level strings can be found here:
<https://docs.python.org/3/library/logging.html#logging-levels>

When the switch is not used, we set the default level to INFO.

Example:

```bash
--log-cli-level=DEBUG
```

### Common templates and golden images

As of 2.6, VMs using common templates will require an existing golden image PVC.
Golden image name - SRC_PVC_NAME
Golden images namespace parameter - SRC_PVC_NAMESPACE (default: openshift-virtualization-os-images)
The VM's created PVC will have the same name as the VM (NAME parameter).

- Fixtures prefixed with "golden_image_data_volume" are used to create golden image
  DV.
- Fixtures prefixed with "golden_image_vm" are used to create a VM from template, based on a golden
  image PVC.
  When using the fixtures, note their scopes. As golden image may be created once per class,
  it can be used by multiple VMs created under that class (scoped as function).

## Running tests in disconnected environment (inside the container)

If your cluster does not have access to internal RedHat network - you may build openshift-virtualization-tests
container and run it directly on a cluster.

### Building and pushing openshift-virtualization-tests container image

Container can be generated and pushed using make targets.

```
make build-container
make push-container
```

##### optional parameters

```
export IMAGE_BUILD_CMD=<docker/podman>               # default "docker"
export IMAGE_REGISTRY=<container image registry>     # default "quay.io"
export REGISTRY_NAMESPACE=<your quay.io namespace>   # default "openshift-cnv"
export OPERATOR_IMAGE_NAME=<image name>              # default "openshift-virtualization-tests"
export IMAGE_TAG=<the image tag to use>              # default "latest"
```

### Running containerized tests examples

For running tests you need to have access to artifactory server with images.
Environment variables `ARTIFACTORY_USER` and `ARTIFACTORY_TOKEN` expected to be set up for local runs.
For these credentials, please contact devops QE focal point via cnv-qe slack channel.

Also need to create the folder which should contain `kubeconfig`, binaries `oc`, `virtctl` and **ssh key** for access
to nodes. This folder should be mounted to container during the run.

#### Running default set of tests

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

# Network utility container

Check containers/utility/README.md

# Development

openshift-virtualization-tests is a public repository under the RedHatQE organization on GitHub.

## Clone openshift-virtualization-tests repo

```bash
git clone https://github.com/RedHatQE/openshift-virtualization-tests.git
```

## Make a pull request

```bash
cd openshift-virtualization-tests
git checkout <base_branch (main / cnv-4.15 / etc.)>
git pull
git checkout -b <name-your-local-branch>
<make your changes>
<run pre-commit>
git add <changed files>
git commit -m "<Your commit message>"
git push origin <your-local-branch>
```

Go to GitHub, open a Pull request for a relevant base branch:

```bash
https://github.com/RedHatQE/openshift-virtualization-tests/compare/<name-your-local-branch>
```

## Make changes to the existing pull request

```bash
git checkout -b <your-local-branch>
<make your changes>
<run pre-commit>
git add <changed files>
git commit -m "<Your commit message - new changes>"
git pull origin/<base_branch> (it does fetch + rebase)
git push origin <your-local-branch>
```

## How-to verify your patch

Determining the depth of verification steps for each patch is left for the
author and their reviewer. It's required that the procedure used to verify a
patch is listed in comments to the review request.

### Check the code

We use checks tools that are defined in .pre-commit-config.yaml file
To install pre-commit:

```bash
pip install pre-commit --user
pre-commit install
pre-commit install --hook-type commit-msg
```

Run pre-commit:

```bash
pre-commit run --all-files
```

pre-commit will try to fix the errors.
If some errors where fixed, git add & git commit is needed again.
commit-msg use gitlint (<https://jorisroovers.com/gitlint/>)

To check for PEP 8 issues locally run:

```bash
tox
```

### Run the tests via Jenkins job

#### Build and push a container with your changes

Comment your GitHub PR:

```bash
/build-and-push-container
```

You can add additional arguments when creating the container. Supported arguments can be found in the Dockerfile
and Makefile of the openshift-virtualization-tests repository.

For example, this command will create a container with the openshift-virtualization-tests PR it was run against and the latest commit of
a wrapper PR:

```bash
/build-and-push-container --build-arg OPENSHIFT_PYTHON_WRAPPER_COMMIT=<commit_hash>
```

Container created with the `/build-and-push-container` command is automatically pushed to quay and can be used by
Jenkins test jobs for verification (see `Run the Jenkins test jobs for openshift-virtualization-tests` section for more details).

#### Run the Jenkins test jobs for openshift-virtualization-tests

Open relevant test jobs in jenkins
Click on Build with Parameters.
Under `CLUSTER_NAME` enter your cluster's name.
Under `IMAGE_TAG` enter your image tag, example: openshift-virtualization-tests-github:pr-<pr_number>
This same field can be used to test a specific container created from a openshift-virtualization-tests PR.

To pass parameters to pytest command add them to `PYTEST_PARAMS`.
for example `-k 'network'` will run only tests that match 'network'

### Generate source docs

```bash
cd docs
make html
```

The HTML file location is:
docs/build/html/index.html

### Tweaks

##### unprivileged_client

To skip `unprivileged_client` creation pass to pytest command:
```bash
--tc=no_unprivileged_client:True
```

#### Run command on nodes

`ExecCommandOnPod` is used to run command on nodes

##### Example

`workers_utility_pods` and `control_plane_utility_pods` are fixtures that hold the pods.

```python
pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
out = pod_exec.exec(command=cmd, ignore_rc=True)
```

##### Known Issues

pycurl may fail with error:
ImportError: pycurl: libcurl link-time ssl backend (nss) is different from compile-time ssl backend (none/other)

To fix it:

```bash
export PYCURL_SSL_LIBRARY=nss # or openssl. depend on the error (link-time ssl backend (nss))
uv run pip uninstall pycurl
uv run pip install pycurl --no-cache-dir
```

## Commit Message

It is essential to have a good commit message if you want your change to be reviewed.

- Start with a short one line summary
- Followed by one or more explanatory paragraphs
- Use the present tense (fix instead of fixed)
- Use the past tense when describing the status before this commit
- Add a link to the related jira card (required for any significant automation work)
  - `jira-ticket: https://issues.redhat.com/browse/<jira_id>`
  - The card will be automatically closed once PR is merged
