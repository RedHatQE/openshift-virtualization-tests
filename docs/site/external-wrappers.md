# External Ecosystem Wrappers

This page documents the external ecosystem wrappers used across the test suite for command execution and OpenShift resource management. Do not use standard library `subprocess` or construct raw Kubernetes YAML dicts.

---

## `pyhelper-utils` (Shell Execution)

The `pyhelper-utils` library is the mandatory method for executing local commands and SSH commands. Never use `subprocess.run()`.

### `run_command`
Executes a local shell command securely as a subprocess.

| Parameter       | Type        | Default | Description |
|-----------------|-------------|---------|-------------|
| `command`       | `list[str]` | (Required) | The command to execute, typically parsed via `shlex.split()`. |
| `check`         | `bool`      | `True`  | If `True`, raises `pyhelper_utils.exceptions.CommandExecFailed` if the command fails. |
| `verify_stderr` | `bool`      | `True`  | If `True`, validates standard error output. |

```python
from pyhelper_utils.shell import run_command
import shlex

# Example: Run command locally and capture output
success, stdout, stderr = run_command(
    command=shlex.split("oc get pods -n my-namespace"),
    check=False,
    verify_stderr=False
)
```

### `run_ssh_commands`
Executes commands on a remote host via SSH.

| Parameter      | Type                           | Default | Description |
|----------------|--------------------------------|---------|-------------|
| `host`         | `rrmngmnt.Host` / `SSHClient`  | (Required) | The SSH connection object, typically accessed via `vm.ssh_exec`. |
| `commands`     | `list[str] \| str`             | (Required) | The command(s) to execute on the remote host. |
| `check_rc`     | `bool`                         | `True`  | If `True`, validates the command's return code. |
| `wait_timeout` | `int`                          | `120`   | Maximum time (seconds) to wait for the command to complete. |
| `sleep`        | `int`                          | `1`     | Polling interval (seconds) while waiting. |

```python
from pyhelper_utils.shell import run_ssh_commands
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC

# Example: Execute command inside a VM
output = run_ssh_commands(
    host=vm.ssh_exec,
    commands=["cat", "/etc/os-release"],
    wait_timeout=TIMEOUT_2MIN,
    sleep=TIMEOUT_5SEC
)[0]
```

---

## `ocp-resources` (OpenShift Resource Management)

The `ocp-resources` package provides Pythonic abstractions for OpenShift and Kubernetes resources.

### OpenShift Resource Classes
Object-oriented wrappers for OpenShift APIs. Instead of passing dictionaries to Kubernetes client functions, instantiate and use these classes (e.g., `VirtualMachine`, `DataVolume`, `Pod`, `Namespace`).

| Parameter   | Type            | Default | Description |
|-------------|-----------------|---------|-------------|
| `name`      | `str`           | `None`  | The name of the resource. |
| `namespace` | `str`           | `None`  | The namespace where the resource resides. |
| `client`    | `DynamicClient` | `None`  | A preconfigured Kubernetes dynamic client. |
| `teardown`  | `bool`          | `True`  | If `True`, deletes the resource when exiting a context manager block. |
| `body`      | `dict`          | `None`  | Optional raw dictionary of the resource definition (e.g. `spec`). |

```python
from ocp_resources.virtual_machine import VirtualMachine

# Use context managers to ensure automatic cleanup
with VirtualMachine(
    name="test-vm",
    namespace="my-namespace",
    body=vm_dict_body
) as vm:
    # Interaction logic here
    pass
```

> **Note:** See [Resource Lifecycle & Validation](resource-lifecycle.html) for detailed guidelines on the context manager strategy.

### Resource Lifecycle Methods
All resource objects inherit lifecycle state mechanisms from the base `Resource` class.

| Method | Description |
|--------|-------------|
| `.create()` | Explicitly creates the resource if not using a context manager. |
| `.delete()` | Explicitly deletes the resource. |
| `.wait_for_condition(condition, status, timeout)` | Blocks until the given API condition equals the specified boolean status. |
| `.wait_for_status(status, timeout)` | Blocks until the `.status.phase` (or similar) matches the given status string. |

```python
# Example: Waiting for a specific condition
vm.wait_for_condition(
    condition=VirtualMachine.Condition.READY,
    status=True,
    timeout=120
)

# Example: Using exists property
if vm.exists:
    vm.delete()
```

### `ResourceEditor`
Provides a context manager or explicit execution block to safely patch API resources and optionally rollback.

| Parameter  | Type   | Default | Description |
|------------|--------|---------|-------------|
| `patches`  | `dict` | (Required) | A dictionary mapping the `Resource` object to a nested dictionary representing the patch payload. |

```python
from ocp_resources.resource import ResourceEditor

# Example: Update a field using the context manager (auto-rolls back if applicable)
with ResourceEditor(patches={vm: {"spec": {"running": False}}}):
    vm.wait_for_status(status=vm.Status.STOPPED)

# Example: Permanent update via direct execution
ResourceEditor(patches={node: {"metadata": {"labels": {"test-label": "true"}}}}).update()
```

---

## `openshift-python-wrapper` (`ocp_utilities`)

Provides helper modules that wrap complex OpenShift components like Prometheus monitoring and infrastructure polling.

### `Prometheus`
Simplifies querying the OpenShift observability stack.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `client`  | `DynamicClient` | (Required) | The OpenShift dynamic client instance. |

```python
from ocp_utilities.monitoring import Prometheus

# Example: Execute a PromQL query
prometheus = Prometheus(client=client)
query_results = prometheus.query("kubevirt_vmi_phase_count")

for metric in query_results:
    print(metric["metric"], metric["value"])
```

### `get_pods_by_name_prefix`
Helper utility to fetch running pods dynamically based on their prefix.

| Parameter   | Type  | Default | Description |
|-------------|-------|---------|-------------|
| `prefix`    | `str` | (Required) | The string prefix of the pod name. |
| `namespace` | `str` | (Required) | Target namespace to search. |

```python
from ocp_utilities.infra import get_pods_by_name_prefix

# Example: Find all virt-launcher pods
virt_launcher_pods = get_pods_by_name_prefix(
    prefix="virt-launcher",
    namespace=vm.namespace
)
```

> **Tip:** You can review how test setups apply context managers and these utilities by reading the [Pytest Fixture Strategy](fixture-strategy.html) page.

## Related Pages

- [Project Utilities](utilities-reference.html)
- [Implementing New Tests](implementing-tests.html)
- [Virtualization Tests](virt-tests.html)
