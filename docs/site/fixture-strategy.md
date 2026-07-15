# Pytest Fixture Strategy

Fixtures are the backbone of test state management in the `openshift-virtualization-tests` suite. They handle resource creation, configuration injection, and teardown logic. Because the test suite interacts with complex, stateful OpenShift clusters, mastering our fixture strategy is critical to writing reliable, independent, and fast tests.

This guide explains how fixtures are organized across `conftest.py` files, strict naming conventions, scoping rules, and dependency management.

---

## The Big Picture: `conftest.py` Architecture

To avoid a massive, unmaintainable global state, we strictly layer our `conftest.py` files. Fixtures must be placed as close to their usage as possible, moving to broader shared directories only when proven necessary.

| Location | Purpose | Rules |
| :--- | :--- | :--- |
| **Root `conftest.py`**<br>`/conftest.py` | Pytest hooks and global configuration. | **NO fixtures.** Extract complex logic into pytest plugins instead. |
| **Shared Conftest**<br>`tests/conftest.py` | Exposes broadly shared fixtures across all test domains. | **Import only.** Do not write fixture logic directly here. Import from `tests/fixtures/`. |
| **Domain Fixtures**<br>`tests/fixtures/<domain>/` | Domain-specific modules providing reusable setups (e.g., `tests/fixtures/network/cluster.py`). | Group by domain. Only place fixtures here if used by multiple feature directories. |
| **Feature Conftest**<br>`tests/<domain>/<feature>/conftest.py` | Local feature setups (e.g., `tests/network/l2_bridge/conftest.py`). | The default home for new fixtures. Move up to shared locations only when another test domain needs them. |

> **Note:** Fixture files must ONLY contain fixtures. Helper functions, utility logic, and constants belong in the `utilities/` directory.

---

## Key Concepts and Mandatory Rules

### 1. Noun-Based Naming

Fixtures must describe **what they provide**, not the action they perform. They act as injected resources, not functions.

*   ✅ **Correct:** `vm_with_disk`, `migrated_vm`, `isolated_namespace`
*   ❌ **Incorrect:** `create_vm_with_disk`, `migrate_vm`, `setup_namespace`

### 2. The Single Action Principle

A fixture must perform exactly **ONE action** (single responsibility). If a test requires a namespace, a network attachment definition, and a VirtualMachine, use three separate fixtures injected into the test. Do not create a monolithic `setup_complex_vm_environment` fixture.

### 3. Yield vs. Return

Always `yield` resources rather than `return` them, even if the fixture does not require complex teardown. This ensures the test can inspect the resource, and any required cleanup logic executes predictably after the test completes.

```python
import pytest
from ocp_resources.namespace import Namespace

@pytest.fixture(scope="module")
def isolated_namespace():
    with Namespace(name="test-isolated-ns") as ns:
        yield ns
```

### 4. Dependency Injection Ordering

When a fixture relies on other fixtures, request them in this strict order:
1. Pytest native fixtures (e.g., `request`, `tmpdir`)
2. Session-scoped fixtures
3. Module/Class-scoped fixtures
4. Function-scoped fixtures

> **Warning:** Mixing scope ordering can lead to `ScopeMismatch` errors from pytest, especially when a broader-scoped fixture attempts to depend on a narrower-scoped one.

---

## Fixture Scoping Rules

Proper scoping minimizes API load on the OpenShift cluster and speeds up test execution. Use the narrowest scope necessary, but take advantage of broader scopes for immutable or expensive setups.

| Scope | When to use | Examples |
| :--- | :--- | :--- |
| `scope="function"` | **(Default)** Use when the setup must be completely isolated, modifies state, or creates per-test resources. | Individual VMs, DataVolumes, mutating workloads. |
| `scope="class"` | Use for setup shared across a specific test class. | Shared network configurations for a subset of test cases. |
| `scope="module"` | Use for expensive setups within a single test file (`test_*.py`). | A target VM used by multiple non-destructive connection tests. |
| `scope="session"` | Use for setups that persist across the entire test run. | Base storage classes, global namespaces, cluster-wide feature gates. |

> **Warning:** **NEVER** use a broader scope (like `module` or `session`) if the test modifies the resource's state. If Test A deletes a disk from a module-scoped VM, Test B will fail when it expects that disk to exist.

---

## How it Affects the User

### Parameterized Fixtures
When tests require different permutations of a setup (e.g., testing multiple storage protocols), use parameterized fixtures with `request.param`. Use dictionaries for complex parameters.

```python
@pytest.fixture(scope="function", params=[{"protocol": "iscsi"}, {"protocol": "nfs"}])
def storage_endpoint(request):
    protocol = request.param["protocol"]
    # Setup protocol endpoint...
    yield endpoint
```

### Unused but Required Fixtures
If a test requires a fixture for its side effects (like applying a cluster configuration) but does not directly interact with the yielded resource, you **must** use `@pytest.mark.usefixtures`.

*   ✅ **Correct:** Decorating the test or class with `@pytest.mark.usefixtures("cluster_config")`.
*   ❌ **Incorrect:** Requesting `cluster_config` in the test function signature and never referencing the variable.

### Test Independence vs. Dependencies
Tests must be independent. Use shared fixtures to provide resources. Only use `@pytest.mark.dependency` when Test B absolutely must run after Test A (e.g., sequential cluster state transitions). If you use `@pytest.mark.dependency`, a code comment explaining **why** the dependency exists is mandatory.

---

## Related Pages

*   See [Resource Lifecycle & Validation](resource-lifecycle.html) for guidelines on managing OpenShift resources within your fixtures.
*   See [Implementing New Tests](implementing-tests.html) to learn how to inject these fixtures into functional test cases.
*   See [Configuration & Global Contexts](configuration-constants.html) to understand how fixtures leverage global parameters across different cloud and architecture topologies.
