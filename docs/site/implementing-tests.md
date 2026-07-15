# Implementing New Tests

Writing clear, robust, and independent test cases ensures our virtualization features remain stable over time. By following standard patterns for assertions, utility reuse, and infrastructure tagging, you prevent flaky test runs and speed up the review process.

## Prerequisites

* Your development environment must be configured with `uv`. See [Quickstart & Setup](quickstart.html).
* The feature test plan (STP) must be approved and documented.
* Basic understanding of pytest fixtures and OpenShift virtualization primitives.

## Quick Example

The simplest working example of a test verifies VM state transitions. It defines an isolated resource via a fixture, runs the steps sequentially, and asserts conditions directly.

```python
import logging
import pytest

from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    wait_for_vm_interfaces,
)

LOGGER = logging.getLogger(__name__)

@pytest.fixture()
def vm_to_restart(unprivileged_client, namespace):
    name = "vm-to-restart"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm

@pytest.mark.polarion("CNV-1497")
def test_vm_restart(vm_to_restart):
    """
    Test VM restart operations.

    Preconditions:
        - A running Fedora VM exists.

    Steps:
        1. Restart the VM.
        2. Stop the VM.
        3. Start the VM.

    Expected:
        - VM reaches running state and network interfaces are ready.
    """
    LOGGER.info("Restarting VM")
    vm_to_restart.restart(wait=True)

    LOGGER.info("Stopping VM")
    vm_to_restart.stop(wait=True)

    LOGGER.info("Starting VM")
    vm_to_restart.start(wait=True)
    vm_to_restart.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vm_to_restart.vmi)

    assert vm_to_restart.ssh_exec.executor().is_connective(), "Failed to SSH into the restarted VM"
```

## Step-by-Step

Follow these steps to implement a new feature test successfully:

### 1. Write the Test Signature and Docstring
Begin by defining the test function and attaching its required tracking IDs and markers. The docstring MUST contain `Preconditions:`, `Steps:`, and `Expected:` blocks matching your STP.

```python
@pytest.mark.polarion("CNV-1234")
def test_new_feature_validation(my_feature_fixture):
    """
    Verify the new feature behaves correctly.
    ...
    """
```

### 2. Prepare Resources via Fixtures
Never create test objects directly in the test body if they need teardown. Use a pytest fixture with a context manager (using `with`) and `yield` the object to the test. Ensure the fixture does exactly ONE action and is named using a noun (e.g., `vm_with_disk`).

### 3. Implement the Test Logic
Keep tests focused on verifying one aspect. Use existing utility libraries from `utilities/` for common operations instead of calling raw OpenShift YAMLs or subprocesses.

* Use `LOGGER.info` to record phase transitions.
* Use `LOGGER.warning` for missing optional configurations.
* Use `LOGGER.error` inside exception handlers to record full context (what failed, expected vs actual, resource state) before re-raising.

### 4. Assert Expected Outcomes
Replace custom boolean logic with straightforward `assert` statements. Include a clear error message on failure to describe what went wrong.

```python
# Bad
if not vmi.exists:
    raise Exception("VMI is missing")

# Good
assert vmi.exists, f"VirtualMachineInstance {vmi.name} failed to create in {namespace.name}"
```

## Advanced Usage

### Polling Conditions with TimeoutSampler
Hardcoded `time.sleep()` delays cause flaky and slow tests. Whenever you wait for an asynchronous state change, use `TimeoutSampler` from the `timeout_sampler` library.

```python
from timeout_sampler import TimeoutSampler

def _check_condition(resource):
    return resource.status == "Ready"

for sample in TimeoutSampler(
    wait_timeout=60,
    sleep=5,
    func=_check_condition,
    resource=my_resource
):
    if sample:
        break
```

> **Tip:** Do not duplicate timeout exception logs. The `TimeoutSampler` automatically logs the duration and any caught exceptions. Only log additional context if needed.

### Tagging Special Infrastructure
If your test requires specialized cluster hardware or configurations (e.g., GPUs, SR-IOV networks, or DPDK), you must explicitly flag it so CI orchestrates it correctly. Include the `@pytest.mark.special_infra` marker alongside the hardware requirement.

```python
@pytest.mark.special_infra
@pytest.mark.gpu
def test_gpu_workloads(gpu_vm):
    # Specialized hardware test logic
```

For platform-specific differences, see [Multi-Architecture Support](multi-architecture-testing.html).

### Adding Temporary Exclusions
When your test identifies a genuine product defect, do not disable the test entirely. Attach a conditional marker tying it to the issue tracker.

```python
@pytest.mark.jira("CNV-99999", run=False)
def test_known_bug(my_fixture):
    pass
```

For more details on when to use xfail versus Jira markers, see the [Test Quarantine Process](quarantine-process.html).

## Troubleshooting

* **Linter failures locally:** Always commit via `uv run pre-commit run --all-files`. If mypy complains about missing types in new utility functions, add standard Python type hints.
* **Dead code warnings:** Ensure all fixtures and variables are referenced. Unused code will cause `ruff` to fail.
* **Fixture scope issues:** If a test modifies a global resource unexpectedly, check your fixture's scope parameter. Resources that mutate state per-test must use the default `scope="function"`. See [Pull Request Discipline](pr-discipline.html) for guidelines on ensuring clean test implementations.

## Related Pages

- [Test Design Workflow (STP/STD)](test-design-workflow.html)
- [Pytest Fixture Strategy](fixture-strategy.html)
- [Pull Request Discipline](pr-discipline.html)
