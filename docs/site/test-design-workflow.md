# Test Design Workflow (STP/STD)

Design and document your test scenarios before writing automation code to ensure alignment with the Software Test Plan (STP). The Software Test Description (STD) workflow separates test design from implementation, reducing rework by getting approval on behavior and assertions early.

*   An approved Software Test Plan (STP) document or Jira epic.
*   Familiarity with the target feature being tested.
*   See [Implementing New Tests](implementing-tests.html) for general test development context.

Here is a complete Phase 1 STD stub ready for design review:

```python
def test_flat_overlay_ping_between_vms():
    """
    Test that VMs on the same flat overlay network can communicate.

    STP Reference: https://example.com/stp/vm-network

    Markers:
        - gating

    Preconditions:
        - Flat overlay Network Attachment Definition created
        - Client VM running and attached to network
        - Server VM running and attached to network

    Steps:
        1. Get IP address of Server VM
        2. Execute ping from Client VM to Server VM

    Expected:
        - Ping succeeds with 0% packet loss
    """

test_flat_overlay_ping_between_vms.__test__ = False
```

### 1. Write the STD Stub (Phase 1)
Create the test signature and add a Google-format docstring containing exactly three required sections: `Preconditions:`, `Steps:`, and `Expected:`. Assign `__test__ = False` to the function to prevent pytest from collecting the empty test.

> **Tip:** In your `Preconditions:`, name resources by their functional role (e.g., "Client VM", "Target Node") rather than generic labels or implementation fixture names (like "VM-A" or `vm_to_restart`).

### 2. Add Traceability and Markers
Include a direct link to the STP in the docstring (at the module, class, or test level). List intended pytest markers in the `Markers:` section of the docstring. Do not use actual `@pytest.mark` decorators yet.

### 3. Submit the Design PR
Open a pull request containing ONLY the test stubs. Reviewers will validate the design, coverage, and assertion logic before you spend time writing automation.

### 4. Implement the Automation (Phase 2)
After the STD design is approved and merged, write the automation code in a new pull request.

| Task | Phase 1 (Design PR) | Phase 2 (Implementation PR) |
|---|---|---|
| **Test Collection** | `__test__ = False` | Remove `__test__ = False` |
| **Pytest Markers** | Listed in `Markers:` docstring block | Applied via actual `@pytest.mark` decorators |
| **Automation Logic** | None (Docstring only) | Test code, fixtures, and assertions |

```python
import pytest

@pytest.mark.gating
def test_flat_overlay_ping_between_vms(client_vm, server_vm):
    """
    Test that VMs on the same flat overlay network can communicate.

    STP Reference: https://example.com/stp/vm-network
    ...
    """
    server_ip = server_vm.get_ipv4()
    # Ping helper handles the assertion mapped to the 'Expected' docstring section
    client_vm.ping(server_ip)
```

## Advanced Usage

### Shared Preconditions (Class Level)
Group related tests inside a class to share common preconditions. Place shared setup in the class docstring and test-specific setup in the test docstring. To skip an entire class during Phase 1, assign `__test__ = False` at the class level. See [Pytest Fixture Strategy](fixture-strategy.html) for implementing these shared states.

```python
class TestSnapshotRestore:
    """
    Tests for VM snapshot restore functionality.

    Preconditions:
        - Running VM with a data disk
        - Snapshot created from VM
    """
    __test__ = False

    def test_preserves_original_file(self):
        """
        Test that files created before a snapshot are preserved after restore.

        Steps:
            1. Read file /data/original.txt from the restored VM

        Expected:
            - File content equals "data-before-snapshot"
        """
```

### Negative Tests
When verifying failure scenarios, prefix the test description with the `[NEGATIVE]` indicator to clearly communicate the intent.

```python
def test_isolated_vms_cannot_communicate():
    """
    [NEGATIVE] Test that VMs on separate flat overlay networks cannot ping each other.
    ...
    Expected:
        - Ping fails with 100% packet loss
    """
```

### Parametrized Tests
Indicate test matrices using a `Parametrize:` block in your STD. You can also specify inline markers for specific parameter values using `[Markers: ...]`.

```text
    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]
```

## Troubleshooting

*   **Test runs empty or is skipped unexpectedly:** Ensure you removed `__test__ = False` when submitting the Phase 2 implementation.
*   **Review blocked on missing traceability:** Verify the STP link is included in either the module, class, or test docstring. Partial coverage without documented exclusions blocks PR merges.
*   **Tests depending on each other:** Tests must be independent. If strict ordering is required for a sequence of operations, group them in a class and use the `@pytest.mark.incremental` decorator.

## Related Pages

- [Implementing New Tests](implementing-tests.html)
- [Test Quarantine Process](quarantine-process.html)
- [Pull Request Discipline](pr-discipline.html)
