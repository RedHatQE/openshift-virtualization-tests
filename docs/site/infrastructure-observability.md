# Infrastructure & Observability

Validate cluster-wide configurations and ensure OpenShift Virtualization's monitoring pipelines process metrics and alerts correctly. Use the components in the `observability/` and `infrastructure/` domains to verify that workload behavior accurately triggers Prometheus alerts, and that underlying node features (like NUMA and HugePages) are correctly allocated.

### Prerequisites
* A running OpenShift cluster with OpenShift Virtualization installed.
* Test nodes meeting any specialized infrastructure requirements (if testing hardware features like NUMA).
* The monitoring stack configured and accessible via the cluster.

### Quick Example

Test that a Prometheus metric increments after an action. This requires the session-scoped `prometheus` fixture, which automatically authenticates against the cluster's monitoring endpoint.

```python
import pytest
from utilities.monitoring import validate_metrics_value

def test_vmi_creation_metric(prometheus, running_vm):
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=f"kubevirt_vmi_phase_count{{phase='running', name='{running_vm.name}'}}",
        expected_value="1",
        timeout=120
    )
```

### Step-by-Step: Testing Observability & Alerts

When testing metrics and alerts, the test suite relies on polling mechanisms because Prometheus scraping cycles take time.

#### 1. Inject the Prometheus Fixture
Use the globally available `prometheus` fixture located in `tests/conftest.py`. This fixture handles token retrieval, TLS, and client initialization.

#### 2. Query or Validate a Metric
Instead of writing manual loops to poll Prometheus, use the functions in `utilities/monitoring.py`. For simple assertions, `validate_metrics_value` polls until the expected value appears.

```python
from utilities.monitoring import validate_metrics_value

def test_vm_network_metric(prometheus, running_vm):
    # Trigger an action that should emit a metric
    running_vm.stop(wait=True)

    # Wait for the metric to reflect the change
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=f"kubevirt_vmi_phase_transition_time_from_deletion_seconds_count{{name='{running_vm.name}'}}",
        expected_value="1",
    )
```

#### 3. Wait for Firing Alerts
To test that a critical condition triggers a notification in the OpenShift alert manager, use `wait_for_alert`.

```python
from utilities.monitoring import wait_for_alert

def test_vm_crash_alert(prometheus, crashing_vm):
    # Wait up to the timeout for the specific alert to appear in the firing list
    alert = wait_for_alert(
        prometheus=prometheus,
        alert={
            "alertname": "KubeVirtVMHighMemoryUsage",
            "namespace": crashing_vm.namespace
        }
    )
    assert alert, f"Expected memory alert for VM {crashing_vm.name} did not fire"
```

> **Tip:** You can fetch all currently firing alerts for debugging purposes using `get_all_firing_alerts(prometheus)`.

### Advanced Usage

#### Testing Node Infrastructure (NUMA & HugePages)

Infrastructure testing verifies that VMs correctly consume physical cluster resources. Tests targeting specialized hardware must declare `pytest.mark.special_infra` alongside the specific hardware requirement.

```python
import pytest
from tests.utils import assert_numa_cpu_allocation, get_vm_cpu_list, get_numa_node_cpu_dict

# Ensure this test only runs on clusters with NUMA and HugePages
pytestmark = [pytest.mark.special_infra, pytest.mark.hugepages, pytest.mark.numa]

@pytest.mark.polarion("CNV-12367")
def test_numa_cpu_allocation(admin_client, created_vm_cx1_instancetype):
    # Validates CPUs are pinned correctly on NUMA nodes
    assert_numa_cpu_allocation(
        vm_cpus=get_vm_cpu_list(vm=created_vm_cx1_instancetype, admin_client=admin_client),
        numa_nodes=get_numa_node_cpu_dict(vm=created_vm_cx1_instancetype, admin_client=admin_client),
    )
```

> **Warning:** Without `@pytest.mark.special_infra`, hardware-specific tests will fail on generic standard CI clusters. See [Implementing New Tests](implementing-tests.html) for marker definitions.

#### Key Functions and Utilities

Use these utility functions to standardize your tests. Do not reinvent metric polling or hardware assertions.

| Function / Fixture | Scope / Location | Purpose |
| --- | --- | --- |
| `prometheus` | `session` (`tests/conftest.py`) | Provides an authenticated Prometheus client. |
| `validate_metrics_value` | `utilities/monitoring.py` | Polls Prometheus until a metric evaluates to an exact string/integer. |
| `wait_for_alert` | `utilities/monitoring.py` | Polls the AlertManager for a firing alert matching the given dictionary. |
| `get_metrics_value` | `utilities/monitoring.py` | Performs a single Prometheus query and returns the current metric value. |
| `assert_numa_cpu_allocation` | `tests/utils.py` | Verifies CPU requests match the physical NUMA topology boundaries. |
| `verify_hugepages_1gi` | `tests/utils.py` | Verifies the target nodes have 1Gi HugePages allocated and available. |

### Troubleshooting

* **Metrics taking too long to appear:** The default scrape interval in OpenShift Virtualization is typically 30 seconds. If `validate_metrics_value` times out, increase the timeout parameter (e.g., `timeout=120`) to allow at least two full scrape cycles. See [Resource Lifecycle & Validation](resource-lifecycle.html) for best practices on timeouts.
* **Alerts not clearing:** Some Prometheus alerts have lingering evaluation cycles and might remain in `pending` or `firing` states temporarily after a resource is deleted. Use `wait_for_firing_alert_clean_up` from `utilities/monitoring.py` if a test requires a clean slate before starting.
* **Tests skipped on your cluster:** If your infrastructure tests skip immediately, check that your cluster provides the underlying hardware features and that you haven't explicitly filtered out markers using Pytest arguments. See [Running and Filtering Tests](running-tests.html).

## Related Pages

- [Operations & Chaos](operations-chaos.html)
- [Scale & Upgrades Testing](scale-upgrades.html)
- [Networking Tests](network-tests.html)
