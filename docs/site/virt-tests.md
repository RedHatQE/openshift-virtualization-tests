# Virtualization Tests

Test OpenShift Virtualization's core capabilities by orchestrating virtual machine lifecycles, manipulating compute resources via hotplug, triggering live migrations, and validating advanced hardware topologies. This guide covers how to write robust virtualization tests under the `virt/` domain using standardized utilities.

- Access to an OpenShift cluster with the OpenShift Virtualization operator installed.
- Appropriate underlying hardware nodes if writing tests for advanced features (e.g., GPU, SR-IOV, high-resource VMs).

Here is the simplest way to define a virtual machine fixture, start it, and verify its lifecycle states.

```python
import pytest
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    wait_for_vm_interfaces,
)

@pytest.fixture()
def sample_vm(unprivileged_client, namespace):
    name = "sample-vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm

def test_vm_restart(sample_vm):
    """Test restarting an active virtual machine."""
    sample_vm.restart(wait=True)
    sample_vm.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=sample_vm.vmi)
    assert sample_vm.ssh_exec.executor().is_connective(), "VM failed to reconnect after restart"
```

1. **Define the VM in a Fixture**: Use the `with VirtualMachineForTests(...)` context manager in your fixture. This ensures the VirtualMachine custom resource is automatically cleaned up when the test finishes.
2. **Provide OS Configurations**: Use template generators like `fedora_vm_body` or utilize dynamic golden image data sources when specific OS configurations (like RHEL or Windows) are required.
3. **Control State Transitions**: The `running_vm(vm=vm)` helper guarantees the VM reaches the `Running` state before yielding to the test. Within the test, manipulate the lifecycle by calling `vm.start()`, `vm.stop()`, or `vm.restart()` with the `wait=True` parameter.
4. **Validate Interfaces**: Always call `wait_for_vm_interfaces()` before attempting SSH connections. OpenShift Virtualization requires time to provision and attach the underlying network interfaces to the guest OS.

## Advanced Usage

### CPU and Memory Hotplug

Testing resource hotplugging involves patching the VM specification while the virtual machine instance is running, and confirming the guest OS successfully registers the new limits.

```python
from tests.utils import (
    hotplug_spec_vm,
    wait_for_guest_os_cpu_count,
    assert_guest_os_memory_amount
)
from utilities.constants.virt import SIX_CPU_SOCKETS, SIX_GI_MEMORY

def test_hotplug_resources(sample_vm):
    # Hotplug CPU and wait for guest recognition
    hotplug_spec_vm(vm=sample_vm, sockets=SIX_CPU_SOCKETS)
    wait_for_guest_os_cpu_count(vm=sample_vm, spec_cpu_amount=SIX_CPU_SOCKETS)

    # Hotplug Memory and verify
    hotplug_spec_vm(vm=sample_vm, memory_guest=SIX_GI_MEMORY)
    assert_guest_os_memory_amount(vm=sample_vm, spec_memory_amount=SIX_GI_MEMORY)
```

> **Warning:** Negative tests simulating reductions in CPU sockets or memory should capture `UnprocessibleEntityError` exceptions or explicitly assert that a restart is required, as the virtualization API prevents active downscaling.

### Live Migration Validation

To verify a VM can successfully migrate to another node without losing state or network connectivity, use the built-in migration utility. It handles creating the `VirtualMachineInstanceMigration` object and verifying connectivity post-migration.

```python
from utilities.virt import migrate_vm_and_verify

def test_vm_migration(admin_client, sample_vm):
    migrate_vm_and_verify(vm=sample_vm, client=admin_client, check_ssh_connectivity=True)
```

### Hardware Verification via virt_special_infra_sanity

The `tests/virt/conftest.py` file includes a `virt_special_infra_sanity` session-scoped fixture that validates cluster hardware capabilities before test collection finishes. When writing tests that require specialized nodes, you must apply the correct markers so the suite can assert node health early.

| Pytest Marker | Action in `virt_special_infra_sanity` |
| --- | --- |
| `@pytest.mark.gpu` | Verifies cluster has nodes with supported NVIDIA GPUs and lacks incompatible DPDK profiles. |
| `@pytest.mark.sriov` | Validates that at least one worker node has SR-IOV network cards configured. |
| `@pytest.mark.high_resource_vm` | Checks the platform (e.g., bare-metal) and ensures nodes advertise required hardware virtualization extensions (`vmx` or `svm`). |
| `@pytest.mark.descheduler` | Confirms the `kube-descheduler` operator is functional and nodes possess the `psi=1` kernel argument. |

> **Tip:** If hardware requirements are missing, `virt_special_infra_sanity` exits the execution safely rather than allowing hundreds of tests to fail with obscure resource errors. Always ensure your new advanced tests are tagged with the right infra markers.

## Troubleshooting

- **`UnsupportedGPUDeviceError` during test collection**: Ensure you haven't assigned `@pytest.mark.gpu` to a test running on an architecture or cluster profile missing the required `GPU_CARDS_MAP` hardware.
- **Tests hanging on `running_vm`**: This usually indicates the node is overcommitted and the VirtLauncher pod is stuck in a `Pending` state. Check your namespace quotas or use the `node_with_most_available_memory` fixture to pin large VMs.

For more information, explore:
- See [Resource Lifecycle & Validation](resource-lifecycle.html) for timeout handling and resource interactions.
- See [Pytest Fixture Strategy](fixture-strategy.html) to understand how to share golden image variables across classes.
- See [Multi-Architecture Support](multi-architecture-testing.html) for applying node architecture conditional blocks in hardware virtualization tests.

## Related Pages

- [Networking Tests](network-tests.html)
- [Storage Tests](storage-tests.html)
- [Running and Filtering Tests](running-tests.html)
