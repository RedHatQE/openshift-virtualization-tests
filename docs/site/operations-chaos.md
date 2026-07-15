# Operations & Chaos

Evaluate OpenShift Virtualization robustness under duress, execute disruptive component testing, and validate disaster recovery mechanics. Operations and chaos testing ensures your system gracefully handles data loss, ungraceful node restarts, disrupted storage paths, and pod terminations without permanently degrading workloads.

## Prerequisites

*   A running OpenShift cluster with OpenShift Virtualization deployed.
*   OpenShift API for Data Protection (OADP) configured (if executing `data_protection/` test cases).
*   Correct markers specified for execution: `@pytest.mark.chaos` is required for standard disruption tests.
*   The `multiprocessing_start_method_fork` fixture activated (usually via `pytestmark`) for suites relying on continuous background process failures.

## Quick Example: Component Disruption

To verify that VirtualMachines can still be deployed and managed when control-plane pods are repeatedly deleted, utilize the parameterized `pod_deleting_process` indirect fixture.

```python
import pytest
from ocp_resources.deployment import Deployment
from utilities.constants.namespaces import NamespacesNames
from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_5MIN
from utilities.virt import running_vm

pytestmark = [
    pytest.mark.chaos,
    pytest.mark.usefixtures(
        "multiprocessing_start_method_fork",
        "chaos_namespace",
        "cluster_monitoring_process"
    ),
]

@pytest.mark.parametrize(
    "chaos_vms_list_rhel9, pod_deleting_process",
    [
        pytest.param(
            {"number_of_vms": 3},
            {
                "pod_prefix": "apiserver",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_APISERVER,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
        )
    ],
    indirect=True,
)
def test_pod_delete_openshift_apiserver(pod_deleting_process, chaos_vms_list_rhel9):
    """
    Verifies that VMs can be deployed while openshift-apiserver pods are continuously deleted.
    """
    for vm in chaos_vms_list_rhel9:
        vm.deploy()
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
```

> **Note:** The `pod_deleting_process` fixture initiates a background process that consistently deletes a defined ratio (e.g., `0.5` or 50%) of the target pods at a set interval while your test logic executes.

## Implementing Chaos Experiments

When designing disruptive tests, the primary sequence is to introduce an active interference, perform a standard workload procedure (e.g., VM creation), and assert the system tolerated the disruption.

### 1. Select the Disruption Vector
The suite contains various disruption patterns. Use the utilities in `tests/chaos/utils.py` to trigger them:
*   **Process Manipulation:** Call `create_pod_deleting_process` or `create_pod_deleting_thread` to force restarts of critical operators or daemonsets.
*   **Hardware and Node Interference:** Yield the `rebooting_node` generator to suddenly restart cluster nodes where workloads reside.

### 2. Track System Degradation
Add `cluster_monitoring_process` (scoped at the module level in `tests/chaos/conftest.py`) to your test's `usefixtures` list. This parallel worker logs pod, daemonset, and node states out to a `chaos-monitoring.txt` log file so you can correlate system health with any test failures.

### 3. Assert Component Recovery
Always confirm the system heals after the disruption event finishes. Use `pod_deleting_process_recover` to poll deployments and daemonsets until they report full health and replica matching before passing the test.

## Advanced Usage

### Data Protection & Disaster Recovery (OADP)

The `tests/data_protection/oadp/` directory evaluates snapshot, backup, and restore capabilities via Velero. The aim is to ensure workload data, such as database files within a VM, remains perfectly intact when restored.

```python
import pytest
from ocp_resources.datavolume import DataVolume
from utilities.constants import Images
from utilities.oadp import check_file_in_running_vm
from utilities.constants.oadp import FILE_NAME_FOR_BACKUP, TEXT_TO_TEST

@pytest.mark.parametrize(
    "rhel_vm_with_data_volume_template",
    [
        pytest.param(
            {
                "dv_name": "filesystem-dv",
                "vm_name": "filesystem-vm",
                "volume_mode": DataVolume.VolumeMode.FILE,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("velero_restore_first_namespace_with_datamover")
def test_backup_vm_data_volume_template_with_datamover(rhel_vm_with_data_volume_template):
    # Validates the VM state was perfectly restored by Velero
    check_file_in_running_vm(
        vm=rhel_vm_with_data_volume_template,
        file_name=FILE_NAME_FOR_BACKUP,
        file_content=TEXT_TO_TEST
    )
```

**Key OADP Fixtures:**
*   `velero_backup_single_namespace`: (Session scoped) Triggers a backup of a dedicated namespace, polling Velero until it confirms partial or full completion.
*   `velero_restore_first_namespace_with_datamover`: (Module scoped) Restores resources using a CSI Datamover, yielding when workloads report completion.
*   `rhel_vm_with_data_volume_template`: Seeds VMs with test data natively before a backup initiates.

### Host IO & CPU Stressing

To validate performance boundaries, trigger host-level utilities like `stress-ng` using the `chaos_worker_background_process` parameterized fixture.

```python
@pytest.mark.parametrize(
    "chaos_worker_background_process",
    [
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                "background_command": "stress-ng --io 5 -t 120s",
                "process_name": "stress-ng",
            },
        ),
    ],
    indirect=True,
)
def test_host_io_stress(
    vm_with_nginx_service,
    nginx_monitoring_process,
    chaos_worker_background_process,
):
    chaos_worker_background_process.join()
    nginx_monitoring_process.join()

    assert nginx_monitoring_process.exitcode == 0, "NGINX failed to respond under IO load"
    assert chaos_worker_background_process.exitcode == 0, "Stress workload failed to execute"
```

## Functions and Modules Summary

| Resource / Module | Path | Purpose |
| :--- | :--- | :--- |
| **Disruption Utils** | `tests/chaos/utils.py` | Contains process threads (`create_pod_deleting_thread`), process killers, and node reboot handlers. |
| **Chaos Standard** | `tests/chaos/standard/test_standard.py` | Standard experimental test flows asserting VM operation during pod starvation and component destruction. |
| **OADP/Velero Workflows** | `tests/data_protection/oadp/test_velero.py` | Full-stack backup and CSI data-mover restore validation routines across file and block volume modes. |
| **OADP Verification** | `utilities.oadp` | Utility operations specific to reading marker files off recovered VMs (`check_file_in_running_vm`). |

> **Tip:** Do not write defensive polling loops (e.g. infinite retries waiting for an API response) when a failure condition is actively invoked. Use native timeout patterns, and if a workload action fails during chaos, the test should explicitly fail. See [Resource Lifecycle & Validation](resource-lifecycle.html) for more on safe polling mechanics.

## Related Pages

- [Infrastructure & Observability](infrastructure-observability.html)
- [Scale & Upgrades Testing](scale-upgrades.html)
- [Test Quarantine Process](quarantine-process.html)
