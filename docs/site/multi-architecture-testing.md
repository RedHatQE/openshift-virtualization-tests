# Multi-Architecture Support

Multi-architecture testing support enables the test suite to execute seamlessly against diverse cluster topologies, including single-architecture (homogeneous) and multi-architecture (heterogeneous) OpenShift environments. By avoiding hardcoded assumptions about the underlying CPU architecture (`amd64`, `arm64`, `s390x`), you ensure that OpenShift Virtualization tests are portable, reliable, and compliant across different hardware platforms.

> **Note:** Tests are evaluated on `amd64` by default. When tests target non-x86 hardware or heterogeneous environments, the framework dynamically adjusts configuration data, OS images, and node selectors to match the target architecture.

## The Big Picture: Cluster Types and Run Modes

The test framework detects the cluster's topology using worker node labels. Based on the configuration passed via the `--cpu-arch` flag, the test suite executes in one of three modes:

| Test Suite Scope | Cluster Type | `--cpu-arch` value | What Happens at Runtime |
| :--- | :--- | :--- | :--- |
| **Standard Regression** | Homogeneous (Single Arch) | *(Omitted)* | Auto-detects architecture from node labels. Runs standard regression tests on that specific architecture. |
| **Multiarch Regression** | Heterogeneous (Multi Arch) | Single value (e.g., `arm64`) | Scopes standard regression tests strictly to nodes matching the specified architecture. |
| **Multiarch-Dedicated** | Heterogeneous (Multi Arch) | Comma-separated (e.g., `amd64,arm64`) | Only runs tests decorated with `@pytest.mark.multiarch`. Validates cross-architecture scheduling and behaviors. |

> **Warning:** Running with `--cpu-arch=amd64,arm64` disables automatic test filtering and standard helper logic (like single-OS generation). Tests running in this mode must manually filter nodes and orchestrate cross-arch capabilities.

## Key Concepts and Conditional Logic

Designing multi-architecture tests relies on shared platform constants, dynamic fixtures, and conditional logic.

### Platform Constants

Instead of using raw strings, always import architecture definitions from the central constants file `utilities/constants/architecture.py`.

```python
from utilities.constants.architecture import AMD_64, ARM_64, S390X, MULTIARCH
```

### Architecture Fixtures and Scoping

Several built-in fixtures (located in `tests/conftest.py`) provide contextual architecture data to your tests dynamically:

* **`nodes_cpu_architecture`** (Session scope): Returns the CPU architecture string currently being targeted (e.g., `arm64`). Useful for conditionally skipping steps or mutating configurations.
* **`is_s390x_cluster`** (Session scope): A convenience boolean fixture to quickly alter configuration behavior on IBM Z hardware.
* **`schedulable_nodes`** (Session scope): Automatically filters the list of available OpenShift nodes to only return those matching the architecture being tested (defined by `nodes_cpu_architecture`).

### Conditional Logic in Test Design

When a test or fixture must adapt to the platform, use `nodes_cpu_architecture` rather than making external API calls. The framework evaluates these fixtures before resources are instantiated.

**Example: Adapting CPU Model by Architecture (`tests/conftest.py`)**
```python
@pytest.fixture(scope="session")
def host_cpu_model(schedulable_nodes, nodes_cpu_architecture):
    # ARM_64 environments do not expose specific host-model-cpus in the same way x86 does
    if nodes_cpu_architecture == ARM_64:
        return None
    return get_host_model_cpu(nodes=schedulable_nodes)
```

### Explicit Architecture Placement (Multiarch-Dedicated)

When writing multiarch-dedicated tests (tests that explicitly verify cross-architecture functionality), you must hardcode architecture targets in your resource specifications to ensure VMs are placed correctly.

**Example: Instantiating Specific Architecture VMs (`tests/fixtures/network/multiarch.py`)**
```python
@pytest.fixture(scope="class")
def arm_vm(namespace, unprivileged_client):
    spec = base_vmspec()
    spec.template.spec.architecture = ARM_64  # Force ARM placement
    with fedora_vm(namespace=namespace.name, name="arm-vm", client=unprivileged_client, spec=spec) as vm:
        vm.start(wait=True)
        yield vm
```

## How It Affects the User

As a test writer, your interaction with multi-architecture support revolves primarily around using markers and testing isolated conditional logic.

1. **Architecture Exclusion Markers:**
   If a test verifies a feature not supported on a specific architecture, exclude it at the test collection phase rather than using `if/else` inside the test body.
   To run specific suites locally against architectures, you use standard pytest marker invocation (e.g., `pytest -m s390x` or `pytest -m arm64`). The framework assumes `amd64` availability implicitly on unmarked tests.

2. **The `multiarch` Marker:**
   If you are writing a cross-architecture test (e.g., verifying a golden image import to both `amd64` and `arm64` simultaneously), you **must** apply the `@pytest.mark.multiarch` marker.
   ```python
   pytestmark = [pytest.mark.multiarch]
   ```
   > **Tip:** If a non-multiarch test is collected during a dedicated multi-arch run (`--cpu-arch=amd64,arm64`), pytest will raise an `UnsupportedCPUArchitectureError`.

3. **Silent Handling on Homogeneous Clusters:**
   If your multiarch test runs on a standard single-architecture cluster during CI, the framework automatically deselects it at collection time via the `filter_multiarch_tests` hook. You do not need to add defensive skips for environment availability.

## Related Pages

- See [Running and Filtering Tests](running-tests.html) for detailed command-line arguments and test execution workflows.
- See [Configuration & Global Contexts](configuration-constants.html) for understanding how `--tc-file=tests/global_config.py` impacts architecture discovery.
- See [Pytest Fixture Strategy](fixture-strategy.html) for rules regarding fixture implementation and scope mapping.

## Related Pages

- [Running and Filtering Tests](running-tests.html)
- [Scale & Upgrades Testing](scale-upgrades.html)
- [Infrastructure & Observability](infrastructure-observability.html)
