# Scale & Upgrades Testing

Scale and Upgrade testing ensures that OpenShift Virtualization handles extreme limits, massive concurrency, and complex operator lifecycle changes without dropping workloads. For contributors, working in the `tests/scale/` and `tests/install_upgrade_operators/` directories requires a significant mindset shift.

Instead of simple "arrange-act-assert" flows, test developers must carefully choreograph massive cluster state changes, prevent sudden API server exhaustion through staggered batching, sequence operator transitions via strict fixture chains, and prioritize forensic evidence gathering over aggressive teardowns when failures occur.

## The Big Picture

Testing massive scale and product upgrades relies on structured data flow and fixture dependency graphs.

### Scale Testing Architecture Flow

1. **Parameter Ingestion**: Configuration is driven externally (e.g., `tests/scale/scale_params.yaml`), defining OS flavors, storage variants, and batch sizes.
2. **Golden Image Pre-provisioning**: To prevent storage backend DDoS, `DataVolume` clones are deployed at the class level and shared.
3. **Batched Execution**: VMs are spawned and powered on in defined batches with calculated sleep intervals to throttle API server load.
4. **Asynchronous Polling**: Instead of asserting each VM's state sequentially, global samplers evaluate the entire cluster configuration asynchronously.
5. **Fail-Open Debugging**: When massive workloads crash the cluster, default teardowns are suspended to preserve logs for forensic analysis.

### Operator Upgrade Pipeline Flow

The upgrade test framework treats the upgrade process as a pipeline, mapped entirely onto `pytest` fixtures.

1. **Pre-Upgrade Baseline**: Captures active Machine Config Pools (MCP) and firing Prometheus alerts before touching the cluster.
2. **Catalog and Subscription Setup**: Bypasses default OperatorHub sources, applies custom Konflux Image Digest Mirror Sets (IDMS), and updates the HyperConverged Operator (HCO) catalog source.
3. **Trigger Upgrades**: Mutates the subscription channels for CNV or OpenShift to force a new InstallPlan.
4. **Replacement Monitoring**: Actively watches ClusterServiceVersion (CSV) progress, `OperatorCondition` status (`Upgradeable=True`), and operator Pod replacement.
5. **Post-Upgrade Validation**: Ensures VMs migrated successfully and the system stabilized.

## Key Concepts

### Managing Massive State Safely

Scale testing relies on specific utilities and scoping to prevent resource exhaustion and ensure debuggability.

| Name | Type | Scope | Purpose & Location |
|---|---|---|---|
| `failure_finalizer` | Function | N/A | Aborts normal teardown on scale failure, collects `must-gather` logs, and leaves resources intact. (`tests/scale/test_scale_benchmark.py`) |
| `scale_vms` | Fixture | `class` | Translates YAML scale parameters into structured batches of `VirtualMachineForTestsFromTemplate` objects. (`tests/scale/test_scale_benchmark.py`) |
| `all_vms_running` | Function | N/A | Evaluates an entire array of VM objects simultaneously to check if all achieved `RUNNING` status. (`tests/scale/test_scale_benchmark.py`) |

> **Warning:** Never use standard sequential assertions (`for vm in vms: assert vm.ready()`) in scale testing. Always use collective `TimeoutSampler` evaluations to prevent timeout cascades.

### Fixture-Driven Upgrade Routines

Operator upgrades in `tests/install_upgrade_operators/product_upgrade/conftest.py` rely on sequential fixture execution to safely mutate cluster state.

| Fixture Name | Scope | Lifecycle Action |
|---|---|---|
| `cnv_upgrade` | `session` | Global feature flag that determines whether CNV upgrade tests should run. |
| `updated_custom_hco_catalog_source_image` | `function` | Mutates the HCO catalog source with the targeted upgrade test image. |
| `approved_cnv_upgrade_install_plan` | `function` | Approves the newly generated `InstallPlan` to initiate the upgrade. |
| `upgraded_cnv` | `function` | The final execution barrier: waits for CSV `SUCCEEDED` state, `Upgradeable` condition, and pod replacements. |

### Longevity and Upgrade Storms

Tests under `tests/virt/cluster/longevity_tests/` monitor long-running operator resilience. For example, `test_multi_vm_upgrade_and_reboot.py` executes "upgrade storms" — forcing bulk Windows VMs to run internal Windows/WSL2 updates and trigger massive uncoordinated reboots, validating that the underlying CNV operator and storage layers remain stable under sustained stress.

## How it Affects the User

When writing or modifying tests in these domains, adhere to the following behavioral patterns:

* **Embrace the `keep_resources` parameter**: Scale tests must respect external configuration dictating whether to wipe the cluster. Use `fail-open` logic (like `failure_finalizer`) so failures don't destroy hours of state provisioning.
* **Map upgrade steps to fixtures, not test logic**: The core test method (e.g., `test_cnv_upgrade_process` in `tests/install_upgrade_operators/product_upgrade/test_upgrade.py`) should be nearly empty. All heavy lifting, pre-flight checks, and waiting routines must be defined in the requested fixtures.
* **Utilize Pytest Dependencies**: Use `@pytest.mark.dependency()` to string together execution phases.
  * Example: `test_mass_vm_live_migration` relies on the success of `test_scale_vms_running_stability`. If the VMs fail to run, the migration test automatically skips.
* **Know your markers**:
  * `@pytest.mark.scale` isolates volume testing to prevent triggering inside standard CI gating.
  * `@pytest.mark.longevity` flags tests that will consume significant time.
  * `@pytest.mark.gating` applied alongside `@pytest.mark.cnv_upgrade` ensures product upgrades block release pipelines if broken.

## Related Pages

* See [Resource Lifecycle & Validation](resource-lifecycle.html) for detailed patterns on using `TimeoutSampler` to avoid defensive programming and strict timeouts.
* See [Pytest Fixture Strategy](fixture-strategy.html) for rules regarding standard fixture scopes (`session` vs `class`) and noun-based naming.
* See [Operations & Chaos](operations-chaos.html) for adjacent tests regarding node disruption and disaster recovery.
* See [Configuration & Global Contexts](configuration-constants.html) to understand how `global_config.py` interacts with external YAML files for test configurations.

## Related Pages

- [Multi-Architecture Support](multi-architecture-testing.html)
- [Operations & Chaos](operations-chaos.html)
- [Infrastructure & Observability](infrastructure-observability.html)
