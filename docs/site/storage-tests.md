# Storage Tests

Run tests to validate persistent storage, Containerized Data Importer (CDI) behavior, volume modes, and dynamic provisioning. Testing storage capabilities ensures that virtual machines can successfully attach disks, clone images, handle live migrations, and manage data protection under various conditions.

## Prerequisites

* An active OpenShift cluster with virtualization enabled.
* At least one configured StorageClass (CSI drivers preferred).
* For multi-node storage access, a default StorageClass that supports `ReadWriteMany` (RWX) access modes.

## Quick Example

To execute all storage-related tests across the cluster, use the standard storage marker:

```bash
uv run pytest -m storage
```

If you only want to validate environments with a default RWX StorageClass, filter using the specific marker:

```bash
uv run pytest -m rwx_default_storage
```

## Step-by-Step

Testing storage typically revolves around creating DataVolumes, verifying their phases, and ensuring VMs can consume them.

### 1. Import DataVolumes

When verifying CDI capabilities, ensure that DataVolumes can pull from external sources (HTTP, registry) or clone from existing PVCs. Always use OpenShift resource classes for these operations.

```python
from ocp_resources.datavolume import DataVolume

def test_successful_import_secure_image(namespace, storage_class):
    dv = DataVolume(
        name="alpine-import",
        namespace=namespace.name,
        source={"http": {"url": "https://example.com/alpine.qcow2"}},
        size="200Mi",
        storage_class=storage_class.name,
    )
    dv.deploy()
    dv.wait_for_condition(
        condition=DataVolume.Condition.Type.READY,
        status=DataVolume.Condition.Status.TRUE,
        timeout=300,
    )
```

> **Tip:** When creating tests that wait on storage provisioning, always use explicit polling instead of static delays. See [Resource Lifecycle & Validation](resource-lifecycle.html) for timeout handling strategies.

### 2. Validate RWX Workloads

Many Virtualization features, such as live migration and eviction strategies, depend on multiple nodes having read/write access to the same volume. Tag any test that explicitly requires RWX storage with the appropriate marker.

```python
import pytest

@pytest.mark.rwx_default_storage
def test_vm_live_migration_with_shared_disk():
    # Test implementation relies on the presence of an RWX default storage class
    pass
```

## Advanced Usage

### Working with Volume Binding Modes

Storage classes configured with the `WaitForFirstConsumer` binding mode require a pod to request the volume before the underlying storage is provisioned. Tests validating this must explicitly create a consumer pod or start the VM to trigger provisioning.

| Binding Mode | Test Requirement | Verification Strategy |
|---|---|---|
| `Immediate` | None | Check PVC `Bound` status immediately after creation. |
| `WaitForFirstConsumer` | Launch a dummy pod or VM first | Wait for CDI worker pods to start, then verify `Bound` status. |

### Hotplugging Disks

You can validate dynamic disk attachment by hotplugging DataVolumes into running VMs. Ensure you test both the attachment and the removal processes, verifying that the guest OS recognizes the hardware changes.

```python
def test_hotplug_volume_to_vm(running_vm, new_data_volume):
    running_vm.add_volume(name="data-disk", volume_source={"dataVolume": {"name": new_data_volume.name}})

    # Verify disk is visible in the guest

    running_vm.remove_volume(name="data-disk")
```

See [Virtualization Tests](virt-tests.html) for more on VM lifecycle and hardware interactions.

## Troubleshooting

* **Pending DataVolumes:** If a DataVolume remains in a `Pending` state, check if the associated StorageClass uses `WaitForFirstConsumer` binding mode. If so, you must attach the DataVolume to a workload to trigger provisioning.
* **Skipped RWX Tests:** Tests decorated with `@pytest.mark.rwx_default_storage` will fail or be automatically skipped if the cluster does not have a default StorageClass capable of RWX. Verify your CSI driver capabilities.
* **CDI Import Failures:** Check the `cdi-operator` and `cdi-deployment` pods. Missing proxy settings or invalid CA certificates are common culprits when importing images from external registries.

## Related Pages

- [Virtualization Tests](virt-tests.html)
- [Networking Tests](network-tests.html)
- [Infrastructure & Observability](infrastructure-observability.html)
