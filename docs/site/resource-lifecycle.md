# Resource Lifecycle & Validation

Properly managing the lifecycle of OpenShift resources—from creation and readiness polling to teardown—is crucial for maintaining a reliable automation suite. This page details the standard patterns used across the `openshift-virtualization-tests` framework to safely orchestrate test objects and validate cluster states without introducing hidden bugs or flaky behavior.

By strictly adhering to fail-fast methodologies and standardized polling tools, we ensure that infrastructure anomalies are explicitly caught rather than silently ignored.

## The Big Picture: Resource Lifecycle Flow

Every cluster resource (like a VirtualMachine, NetworkAttachmentDefinition, or DataVolume) goes through a strict sequence of phases during a test. Managing this flow correctly ensures that tests remain independent and that teardowns always succeed, even when assertions fail.

| Phase | Action | Enforced Pattern |
|---|---|---|
| **1. Definition** | Declaring the resource configuration. | Use dedicated classes. Never construct raw YAML dictionaries or use raw `subprocess` calls. |
| **2. Creation** | Deploying the resource to the OpenShift cluster. | Instantiated within a pytest fixture (`yield`) or a standard Python `with` context manager. |
| **3. Readiness** | Waiting for the cluster to report the resource as active. | Use the `TimeoutSampler` to poll for readiness. Never block the thread blindly. |
| **4. Validation** | Asserting properties of the running resource. | Trust the object schema. Perform explicit pytest assertions on returned data. |
| **5. Teardown** | Removing the object and releasing cluster compute. | Handled automatically by the context manager exit or the fixture's post-`yield` execution. |

## Key Concepts

### Polling and Timeouts (`TimeoutSampler`)

Network latencies and cluster reconciliation loops mean that objects rarely transition to a "Ready" state instantly. You must proactively poll the cluster.

> **Warning:** NEVER use `time.sleep()` in test loops. Hardcoded sleep intervals make test suites artificially slow and highly prone to flakiness under load.

Instead, always use the `TimeoutSampler` tool. It cleanly encapsulates the polling loop, handles logging on timeouts, and yields control back to the test efficiently.

**Example usage:**
```python
from timeout_sampler import TimeoutSampler

# Poll until the VM reports its status as running
for sample in TimeoutSampler(wait_timeout=120, sleep=5, func=check_vm_status, vm=my_vm):
    if sample == "Running":
        break
```
> **Tip:** Do not duplicate the internal logging of `TimeoutSampler`. Only log additional context (e.g., specific resource configurations) rather than logging "waiting for 5 seconds..." inside your loop.

### Avoiding Defensive Programming

One of the strict rules of this codebase is **No defensive programming**. We believe in a "fail-fast" paradigm. If an OpenShift cluster returns a malformed object or a linter throws an error, the code must break explicitly so the bug is visible.

Do not hide bugs behind fake defaults or empty checks.

**Anti-Patterns (Prohibited):**
* Checking attributes that are guaranteed to exist (`if hasattr(vm, 'name')`).
* Verifying parameters defined strictly by schema.
* Silently swallowing generic exceptions using `try: ... except Exception: pass`.

**Acceptable Defensive Checks (Exceptions):**
1. **Destructors/Cleanup Phase:** Resources may fail during partial initialization; teardowns must safely check for `None` before attempting deletion.
2. **Optional Parameters:** When a configuration argument is explicitly typed as `Type | None = None`.
3. **Lazy Initialization:** Variables strictly intended to populate on first access.
4. **Platform Constants:** Checking if a specific hardware feature is available on `s390x` vs `amd64`.
5. **Unversioned APIs:** Interacting with external endpoints lacking backward compatibility guarantees.

### Exception Contextualization

When a cluster resource encounters an error, stack traces should provide immediate clarity on what resource failed and why. Catching errors and silently returning `False` is prohibited.

If you must catch an exception to transform it, always re-raise it with context to preserve the original stack trace:

```python
try:
    execute_cluster_operation()
except ConnectionError as original_error:
    # Always include expected vs actual states or resource metadata
    raise ConfigurationError(f"Failed to connect to VM {vm.name} on node {node.name}") from original_error
```

## How it Affects the User

For test authors and engineers diagnosing CI failures, these lifecycle guardrails translate to predictable, clear outcomes:

* **No Ghost Failures:** Because teardowns rely on `yield` blocks and context managers, a test crashing midway will not leave orphaned resources consuming memory on the cluster.
* **Readable Stack Traces:** Fail-fast rules combined with explicit exception contextualization mean you immediately see *"VM failed to transition to Running state"* instead of a cryptic `NoneType has no attribute 'status'` deeply buried in a helper function.
* **Deterministic Execution:** Eliminating `time.sleep()` prevents "works on my machine" bugs where slower CI nodes fail solely due to strict hardcoded timings.

## Related Pages

* Explore how to properly implement these concepts in your code on the [Implementing New Tests](implementing-tests.html) guide.
* Learn about injecting your robustly managed resources into test logic using the [Test Design Workflow (STP/STD)](test-design-workflow.html).
* Understand how to condition your lifecycles across different environments in [Configuration & Global Contexts](configuration-constants.html).

## Related Pages

- [Pytest Fixture Strategy](fixture-strategy.html)
- [Configuration & Global Contexts](configuration-constants.html)
- [Project Utilities](utilities-reference.html)
