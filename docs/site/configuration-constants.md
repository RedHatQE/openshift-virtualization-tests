# Configuration & Global Contexts

## What are Configuration and Global Contexts?

In a complex test suite that spans multiple cloud providers, local data centers, and different CPU architectures (amd64, arm64, s390x), relying on hardcoded strings or test-specific setups creates brittle code.

The `openshift-virtualization-tests` framework manages global test context and domain-specific constants centrally. This allows the test suite to:
- Dynamically adapt to the cluster's architecture without manual intervention.
- Provide a consistent set of configuration matrices (e.g., storage classes, networks, instances) across all test runs.
- Prevent typos and duplication by enforcing strict, domain-specific constant files.

By understanding how global config and constants flow through the system, users can easily write tests that scale across any deployment environment.

## The Big Picture: Architecture and Flow

The project splits global parameters into two main categories: **Runtime Configurations** and **Static Domain Constants**.

| Component | Location | Purpose | Dynamic Behavior |
| --- | --- | --- | --- |
| **Global Config** | `tests/global_config.py` | Environment-wide variables, default states, and parametrizing matrices. | Dynamically loads sub-configs (e.g., `global_config_amd64.py`) based on cluster architecture. |
| **Domain Constants** | `utilities/constants/` | Domain-specific static strings (e.g., timeouts, namespaces, component names). | Architecture-specific image URLs are calculated dynamically at module load time. |

### Config Initialization Flow

1. **Architecture Detection:** At test collection time, `utilities.architecture.get_cluster_architecture()` queries Kubernetes Node labels (or reads the `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH` env var in CI) to determine if the cluster is single-arch or `multiarch`.
2. **Sub-config Loading:** `tests/global_config.py` uses `pytest_testconfig` to load the appropriate child configuration file (`tests/global_config_{cluster_type}.py`).
3. **Variable Export:** Variables defined in the module are mapped into a global `config` dictionary, making them accessible to any test that imports them.
4. **Constants Binding:** Domain modules export architecture-specific values dynamically so tests request generic names (e.g., `Images.Rhel.RHEL9_REGISTRY_GUEST_IMG`) and receive the correct URL for the cluster's architecture.

## Key Concepts

### Global Configuration Matrices
`global_config.py` defines large matrices used to parametrize tests across standard permutations. Instead of redefining these in every test file, tests import the matrices directly.

Examples of global matrices include:
- `storage_class_matrix`: Supported storage provisioners and volume modes.
- `nic_models_matrix`: Supported NIC models (virtio, e1000e).
- `run_strategy_matrix`: VirtualMachine run strategies (Manual, Always, Halted).

### Domain-Specific Constants
Constants are strictly organized into domain files under `utilities/constants/` rather than a single monolithic file.

- **`architecture.py`**: Strings for CPU architectures (`AMD_64`, `ARM_64`) and multi-arch logic.
- **`namespaces.py`**: Core OpenShift and Virtualization namespaces.
- **`storage.py`**: Storage classes, datavolume access modes, and volume modes.
- **`timeouts.py`**: Standardized wait times (e.g., `TIMEOUT_5SEC`, `TIMEOUT_5MIN`) to use with `TimeoutSampler`.

> **Note:** The `__init__.py` in `utilities/constants/` restricts what is globally exported. Constants must be explicitly imported from their domain module (e.g., `from utilities.constants.timeouts import TIMEOUT_5MIN`).

### Architecture-Aware Variables
The framework abstracts architecture-specific logic. The `Images` class dynamically resolves the container image path depending on whether the cluster runs on x86, ARM, or s390x.

## How it Affects the User

- **Test Parametrization:** By using `pytest.mark.parametrize` with matrices imported from `global_config.py`, your tests automatically run against the project's standard permutations. If a new storage class becomes standard, adding it to the global matrix automatically expands coverage across all tests using it.
- **Multi-Cloud Portability:** Since you import `default_storage_class` or namespace variables rather than hardcoding `"hostpath-csi"` or `"openshift-cnv"`, your test will run smoothly on AWS, bare metal, or vSphere.
- **Multi-Arch Resilience:** Referencing `Images.Rhel...` guarantees the test won't crash trying to pull an `amd64` image on an `arm64` node.
- **No Magic Strings:** If you need a standard timeout or component name, search the `utilities/constants/` directory. Direct string literals are frequently flagged by maintainers during code review.

## Related Pages
- See [Multi-Architecture Support](multi-architecture-testing.html) for detailed guidelines on writing tests for heterogeneous clusters.
- See [Implementing New Tests](implementing-tests.html) for examples of how to parametrize new test cases using global matrices.
- See [Project Utilities](utilities-reference.html) to understand the helper functions that depend on these constants.
- See [Resource Lifecycle & Validation](resource-lifecycle.html) for how to use `timeouts.py` with polling tools.
- [Pytest Fixture Strategy](fixture-strategy.html)
