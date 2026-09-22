# Project Utilities

This page provides reference documentation for the core domain-specific utilities and custom classes used in `openshift-virtualization-tests`.

See [Resource Lifecycle & Validation](resource-lifecycle.html) for guidelines on using these utilities, and [External Ecosystem Wrappers](external-wrappers.html) for interactions relying on `ocp-resources` or `pyhelper-utils`.

## Utility Overview

| Utility / Class | Purpose | Location |
| :--- | :--- | :--- |
| `VirtualMachineForTests` | Primary context manager and object representing a test VM. | `utilities/virt.py` |
| `BaseVirtualMachine` | Foundational class for loading existing VM resources from the API. | `libs/vm/vm.py` |
| `running_vm` | Bootstraps a VM and guarantees it is completely functional. | `utilities/virt.py` |
| `migrate_vm_and_verify` | Orchestrates live migration and verifies success. | `utilities/virt.py` |
| `virtctl_upload_dv` | Uploads local images to DataVolumes or PVCs via virtctl. | `utilities/storage.py` |
| `create_vm_from_dv` | Wraps `VirtualMachineForTests` to quickly spawn VMs from a DataVolume. | `utilities/storage.py` |
| `ping` | Verifies ICMP connectivity from a source VM to a destination IP. | `utilities/network.py` |
| `get_valid_ip_address` | Validates IPv4 or IPv6 formats and dependencies. | `utilities/network.py` |

---

## Virtualization Utilities

### `VirtualMachineForTests`

**Description:** Main wrapper class extending `ocp_resources.virtual_machine.VirtualMachine`. Used to construct, configure, and manage VMs during testing.
**Return Value / Effect:** Yields an unstarted or started VM object depending on usage context. Can generate and update `cloud-init` user data, resource constraints, and SSH configuration.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | `str` | N/A | Name of the Virtual Machine. |
| `namespace` | `str` | N/A | Namespace where the VM will reside. |
| `client` | `DynamicClient` | `None` | OpenShift API client. |
| `memory_guest` | `str` | `None` | Requested memory allocation (e.g., `2Gi`). |
| `cloud_init_data` | `dict` | `None` | Data to inject via `cloud-init`. |
| `ssh` | `bool` | `True` | Inject public SSH keys automatically. |

```python
from utilities.virt import VirtualMachineForTests
from ocp_resources.resource import Resource

with VirtualMachineForTests(
    name="my-test-vm",
    namespace="test-namespace",
    client=admin_client,
    memory_guest="1Gi",
    ssh=True,
) as vm:
    assert vm.instance.status.phase == Resource.Status.STOPPED
```

### `BaseVirtualMachine`

**Description:** A foundational VM class that includes alternative constructors to bind Python instances to existing cluster VMs instead of creating new ones.
**Return Value / Effect:** Returns a bound `BaseVirtualMachine` class capable of modifying existing VM resources.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | `str` | N/A | Name of the existing Virtual Machine. |
| `namespace` | `str` | N/A | Namespace where the VM already exists. |
| `os_distribution` | `dict` | `None` | Pre-existing OS mapping configuration. |

```python
from libs.vm.vm import BaseVirtualMachine

# Instantiate object purely from an existing cluster resource
existing_vm = BaseVirtualMachine.from_existing(
    name="persistent-vm",
    namespace="default",
    client=admin_client,
)
```

### `running_vm`

**Description:** Triggers the VM start process and polls the resource until it is fully available, checking network assignments and `cloud-init` execution.
**Return Value / Effect:** Returns the started `VirtualMachine` instance. Validates interfaces, IP assignments, and prevents silent boot failures.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `vm` | `VirtualMachineForTests` | N/A | Instantiated VM object. |
| `wait_for_interfaces` | `bool` | `True` | Poll until all network interfaces have an IP assigned. |
| `check_ssh_connectivity` | `bool` | `True` | Verify SSH service is running and accessible. |
| `ssh_timeout` | `int` | `120` | Seconds to wait for SSH connectivity. |
| `wait_for_cloud_init` | `bool` | `False` | Wait until cloud-init logs indicate success. |

```python
from utilities.virt import VirtualMachineForTests, running_vm

with VirtualMachineForTests(name="test-vm", namespace="ns", client=client) as vm:
    active_vm = running_vm(
        vm=vm,
        wait_for_interfaces=True,
        wait_for_cloud_init=True,
    )
```

### `migrate_vm_and_verify`

**Description:** Orchestrates live migration by creating a `VirtualMachineInstanceMigration` object and tracks status until successful completion.
**Return Value / Effect:** Returns the completed `VirtualMachineInstanceMigration` object if successful. Modifies cluster state.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `vm` | `VirtualMachine` | N/A | VM target to migrate. |
| `client` | `DynamicClient` | N/A | Cluster Admin client required for migrations. |
| `timeout` | `int` | `720` | Maximum time to wait in seconds. |
| `wait_for_interfaces` | `bool` | `True` | Re-validate network stack post-migration. |

```python
from utilities.virt import migrate_vm_and_verify

migration_obj = migrate_vm_and_verify(
    vm=my_running_vm,
    client=admin_client,
    timeout=600,
    check_ssh_connectivity=True
)
```

---

## Storage Utilities

### `virtctl_upload_dv`

**Description:** Submits local disk images to the OpenShift cluster by wrapping the `virtctl image-upload` command.
**Return Value / Effect:** Configures a DataVolume or PVC and uploads image bits. Logs the stdout/stderr.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `namespace` | `str` | N/A | Target namespace. |
| `name` | `str` | N/A | Target DataVolume or PVC name. |
| `image_path` | `str` | N/A | Local file path to the QCOW2 or raw image. |
| `size` | `str` | N/A | Size string (e.g., `10Gi`). |
| `client` | `DynamicClient` | N/A | OpenShift API client. |
| `pvc` | `bool` | `False` | Create a PVC directly instead of a DataVolume. |
| `storage_class` | `str` | `None` | Override the default StorageClass. |

```python
from utilities.storage import virtctl_upload_dv

virtctl_upload_dv(
    namespace="storage-tests-ns",
    name="my-custom-dv",
    image_path="/tmp/fedora-cloud.qcow2",
    size="5Gi",
    client=admin_client,
)
```

### `create_vm_from_dv`

**Description:** Generates a full Virtual Machine specification bounded to an existing DataVolume.
**Return Value / Effect:** Yields a `VirtualMachineForTests` context manager initialized from the block volume.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `dv` | `DataVolume` | N/A | Existing, bound DataVolume object. |
| `client` | `DynamicClient` | N/A | Cluster client. |
| `vm_name` | `str` | `"cirros-vm"` | Identifier for the VM. |
| `start` | `bool` | `True` | Automatically call `running_vm`. |

```python
from utilities.storage import create_vm_from_dv

with create_vm_from_dv(
    dv=my_uploaded_dv,
    client=admin_client,
    vm_name="disk-boot-vm",
    start=True
) as vm:
    # VM is fully booted from the DV at this point
    assert vm.instance.status.printableStatus == "Running"
```

---

## Network Utilities

### `ping`

**Description:** Executes an ICMP ping from a source VM's guest OS to a destination IP. Adjusts parameters for IPv4 vs IPv6 automatically.
**Return Value / Effect:** Returns the packet loss percentage (`float` between 0 and 100) or `None` if output parsing fails.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `src_vm` | `VirtualMachine` | N/A | Source VM to execute command via `ssh_exec`. |
| `dst_ip` | `str` | N/A | Destination IP address to ping. |
| `packet_size` | `str` | `None` | Payload data size in bytes. |
| `count` | `int` | `3` | Number of ICMP requests to send. |
| `windows` | `bool` | `False` | Use Windows-specific `ping` syntax. |

```python
from utilities.network import ping

loss_percentage = ping(
    src_vm=client_vm,
    dst_ip="192.168.1.10",
    count=5
)
assert loss_percentage == 0.0, f"Ping failed with {loss_percentage}% loss"
```

### `get_valid_ip_address`

**Description:** Validates strings to guarantee valid IPv4 or IPv6 notation, utilizing the standard `ipaddress` library.
**Return Value / Effect:** Returns `True` if valid, otherwise `False`.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `dst_ip` | `str` | N/A | IP string to validate. |
| `family` | `str` | N/A | The expected family: `"ipv4"` or `"ipv6"`. |

```python
from utilities.network import get_valid_ip_address
from utilities.constants.network import IPV6_STR

if get_valid_ip_address(dst_ip="fd10:244::8c4c", family=IPV6_STR):
    # Proceed with IPv6 configuration checks
    pass
```

---

## Test Integration Patterns

The utility suite interacts closely with test lifecycle mechanics. See [Pytest Fixture Strategy](fixture-strategy.html) and [Running and Filtering Tests](running-tests.html) for detailed configurations.

### Fixture Scoping & Utilities
Utility functions and context managers (like `VirtualMachineForTests`) should match the scope of the fixture wrapping them.

*   `scope="function"`: Creates isolated utilities per test. (e.g., temporary VMs).
*   `scope="module"`: Used for expensive components (e.g., executing `virtctl_upload_dv` in a `tests/storage/conftest.py` setup module).
*   `scope="session"`: Binds cluster-wide administrative changes.

> **Warning:** Never use `__test__ = False` directly on tests implementing these utilities unless it is purely a placeholder for STD (Software Test Description).

### Pytest Markers
Several utilities implicitly assume marker presence:

*   `migrate_vm_and_verify` relies on live-migration topology. Tests using this utility typically belong in `tests/virt/` or are flagged with appropriate markers (e.g., `@pytest.mark.tier2`).
*   Networking utilities like `ping` require advanced cluster configurations if testing SRIOV or DPDK. Mark these with `@pytest.mark.special_infra` and ensure nodes are properly allocated.

## Related Pages

- [External Ecosystem Wrappers](external-wrappers.html)
- [Resource Lifecycle & Validation](resource-lifecycle.html)
- [Configuration & Global Contexts](configuration-constants.html)
