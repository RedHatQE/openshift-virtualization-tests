## Running the tests

### NOTE - Running chaos tests

`chaos` tests disrupt the cluster in different ways in order to build confidence in the robustness of `OpenShift Virtualization`.

To run the chaos tests:

```bash
pytest <pytest_args> -m chaos
```

### Basic run of all tests

```bash
uv run pytest
```

To see optional CLI arguments run:

```bash
uv run pytest --help
```

### Using CLI arguments

CLI arguments can be passed to pytest by setting them in [pytest.ini](../pytest.ini).
You can either use the default pytest.ini file and pass CLI arguments or create a custom one.
For example, add the below under the `addopts` section:
```code
    --skip-artifactory-check
```

Then pass the path to the custom pytest.ini file to pytest:

```bash
uv run pytest -c custom-pytest.ini

```

### Running specific tests
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

### Skip cluster sanity checks
By default, cluster sanity checks are run to make cluster ready for tests.
To skip cluster sanity checks, pass `--cluster-sanity-skip-check` to skip all tests.
To skip specific checks, pass `--cluster-sanity-skip-nodes-check` to skip node checks.
To skip specific checks, pass `--cluster-sanity-skip-storage-check` to skip storage checks.



### Custom global_config to override the matrix value

To override the matrix value, you can create your own `global_config` file and pass the necessary parameters.

Example for AWS cluster:

`--tc-file=tests/global_config_aws.py --storage-class-matrix=px-csi-db-shared`

Example for SNO cluster:

`--tc-file=tests/global_config_sno.py --storage-class-matrix=lvms-vg1`

#### Running tests with an admin client instead of an unprivileged client
To run tests with an admin client only, pass `--tc=no_unprivileged_client:True` to pytest.


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
For example, when tests need to run on storage matrix but only on storage
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


### jira integration
Pytest_jira plugin allows you to link tests to existing tickets.
To use the plugin during a test run, use '--jira.'
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

### Common templates and golden images

As of 2.6, VMs using common templates will require an existing golden image PVC.
Golden image name - SRC_PVC_NAME
Golden images namespace parameter — SRC_PVC_NAMESPACE (default: openshift-virtualization-os-images)
The VM's created PVC will have the same name as the VM (NAME parameter).

- Fixtures prefixed with "golden_image_data_volume" are used to create golden image
  DV.
- Fixtures prefixed with "golden_image_vm" are used to create a VM from template, based on a golden
  image PVC.
  When using the fixtures, note their scopes. As golden image may be created once per class,
  it can be used by multiple VMs created under that class (scoped as function).



## Additional options
There are other parameters that can be passed to the test suite if needed.

```bash
--tc-file=tests/global_config.py
--tc-format=python
--junitxml /tmp/xunit_results.xml
--jira
--jira-url=<url>
--jira-user=<username>
--jira-token==<token>
--jira-no-ssl-verify
--jira-disable-docs-search
```

### Logging

Log file 'pytest-tests.log' is generated with the full pytest output in openshift-virtualization-tests root directory.
For each test failure cluster log is collected and stored under 'tests-collected-info'.


#### Setting log level in command line

To run a test with a log level that is different from the default,
use the --log-cli-level command line switch.
The full list of possible log level strings can be found here:
<https://docs.python.org/3/library/logging.html#logging-levels>

When the switch is not used, we set the default level to INFO.

Example:

```bash
--log-cli-level=DEBUG
```

To see verbose logging of a test run, add the following parameter:

```bash
pytest <test_to_run> -o log_cli=true
```

### Must-gather and data collection
openshift-virtualization-tests would collect must-gather data, pexpect logs, alert data for failure analysis, when --data-collector argument is passed.
Logs will be available under tests-collected-info/ folder for local runs and /data/tests-collected-info for containerized runs.

```bash
pytest <test_to_run> --data-collector
```

To skip must-gather collection on a given module or test, skip_must_gather_collection can be used:

```bash
pytest.mark.skip_must_gather_collection
```

## Network utility container

Check containers/utility/README.md

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
