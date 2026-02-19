> *This document was created with the assistance of Claude (Anthropic).*
# Software Test Description

## Overview

### Test Descriptions as Code

In this repository, **test descriptions are written as docstrings directly in the test code**.
This approach keeps documentation and implementation together, ensuring they stay synchronized and reducing the overhead of maintaining separate documentation.

Each test function includes a comprehensive docstring that serves as the STD, using the **Preconditions/Steps/Expected** format optimized for automation:
- **Preconditions**: Test setup requirements and state
- **Steps**: Numbered, discrete actions (each step maps to code)
- **Expected**: Natural language assertion (e.g., "VM is Running", "File does NOT exist")

The STD format is particularly valuable for:
- **Design First**: Enables test design review before implementation effort
- **Quality Assurance**: Ensures tests are well-documented and can be understood by anyone on the team
- **Maintenance**: Makes it easier to update and maintain tests over time
- **Review**: Facilitates code review by clearly stating expected behavior

---

## Development Workflow

This project follows a **two-phase development workflow** that separates test design from test implementation:

### Phase 1: Test Description PR (Design Phase)

1. **Create test stubs with docstrings only**:
   - Write the test function signature
   - Add the complete STD docstring (Preconditions/Steps/Expected)
   - Include a link to the approved STP (Software Test Plan) in the **module docstring** (top of the test file)
   - Add applicable pytest markers (architecture markers, etc.)
   - Add `__test__ = True` on implemented test(s).  For a single test, add `<test_name>.__test__ = True`

2. **Submit PR for review**:
   - The PR contains only the test descriptions (no automation code)
   - Reviewers evaluate the test design, coverage, and clarity
   - Discussions focus on *what* should be tested and *how* it should be validated

3. **Approval and merge**:
   - Once the test design is approved, merge the PR
   - This establishes the test contract before implementation begins

### Phase 2: Test Automation PR (Implementation Phase)

1. **Implement the test automation**:
   - Add the actual test code to the previously merged test stubs
   - Create any required fixtures
   - Implement helper functions as needed
   - Remove `__test__ = False` from implemented tests
   - If needed, update the test description. This change must be approved by the team's qe tech lead.

2. **Submit PR for review**:
   - Reviewers verify the implementation matches the approved design
   - Focus is on code quality, correctness, and adherence to the STD

3. **Approval, verification and merge**:
   - Once implementation is verified, merge the automation

### Benefits of This Workflow

| Benefit                  | Description                                                    |
|--------------------------|----------------------------------------------------------------|
| **Early Design Review**  | Test design is reviewed before implementation effort is spent  |
| **Clear Contracts**      | The STD serves as a contract between design and implementation |
| **Reduced Rework**       | Design issues are caught early, before automation is written   |
| **Better Documentation** | Tests are always documented before they are implemented        |
| **Easier Planning**      | Test descriptions can be created during sprint planning        |


---

## Automation-Friendly Syntax

To enable consistent parsing and automation, use these conventions in docstrings:

### Assertion Wording (Expected)

Use clear, natural language that maps directly to assertions, for example:

| Wording Pattern                                     | Maps To                                      |
|-----------------------------------------------------|----------------------------------------------|
| `X equals Y`                                        | `assert x == y`                              |
| `X does not equal Y`                                | `assert x != y`                              |
| `VM is "Running"`                                   | `assert vm.status == Running`                |
| `VM is not running`                                 | `assert vm.status != Running`                |
| `File exists` / `Resource x exists`                 | `assert exists(x)`                           |
| `File does not exist` / `Resource x does NOT exist` | `assert not exists(x)`                       |
| `X does not contain Y`                              | `assert y not in x`                          |
| `Ping succeeds` / `Operation succeeds`              | `assert operation()` (no exception)          |
| `Ping fails` / `Operation fails`                    | `assert` raises exception or returns failure |

**Example:**
```text
Expected:
    - VM is Running
    - File content equals "data-before-snapshot"
    - File /data/after.txt does NOT exist
    - Ping fails with 100% packet loss
```

### Exclude new test stubs from pytest collection [customizing-test-collection](https://doc.pytest.org/en/latest/example/pythoncollection.html#customizing-test-collection)

To exclude a whole new module from pytest collection, use:

```python
# test_module_to_ignore.py
__test__ = False

def test_abc():
    assert True # This test will not be collected or run

```

To exclude new test classes from pytest collection, use:

```python
class TestClass:
    __test__ = False
```

To exclude new tests from pytest collection, use:

```python
def test_abc():
    ...

test_abc.__test__ = False
```

### Negative Test Indicator

Mark tests that verify failure scenarios with `[NEGATIVE]` in the description:

```python
def test_isolated_vms_cannot_communicate():
    """
    [NEGATIVE] Test that VMs on separate networks cannot ping each other.
    """

test_isolated_vms_cannot_communicate.__test__ = False
```

### Parametrization Hints

When a test should run with multiple parameter combinations, add a `Parametrize:` section.


### Markers Section

When specific pytest markers are required, list them explicitly.

---

## STD Template

**Key Principles:**
- Each test should verify **ONE thing**
- **Tests must be independent** - no test should depend on another test's outcome
- Related tests are grouped in a **test class**
  - If a test needs a precondition that could be another test's outcome, place the tests under the class in the required order
  - Mention handling of early failures (i.e "fail fast")
- **Shared preconditions** go in the class docstring
- **Test-specific preconditions** (if any) go in the test docstring

### Class-Level Template

```python
class Test<FeatureName>:
    """
    Tests for <feature description>.

    Markers:
        - arm64
        - gating

    Parametrize:
        - storage_class: [ocs-storagecluster-ceph-rbd, hostpath-csi]
        - os_image: [rhel9, fedora]

    Preconditions:
        - <Shared setup requirement>
        - <Another shared requirement>

    """
    __test__ = False

    def test_<specific_behavior>(self):
        """
        Test that <specific ONE thing being verified>.

        Steps:
            1. <The test action to perform>

        Expected:
            - <Natural language assertion, e.g., "VM is Running", "File exists">
        """
```

### Test-Level Template

For standalone tests without related tests:

```python
def test_<specific_behavior>():
    """
    Test that <specific ONE thing being verified>.

    Markers:
        - gating

    Parametrize:
        - os_image: [rhel9, fedora]

    Preconditions:
        - <Setup requirement>
        - <Another requirement>

    Steps:
        1. <The test action to perform>

    Expected:
        - <Natural language assertion, e.g., "VM is Running", "File exists">
    """

test_<specific_behavior>.__test__ = False
```

### Template Components

| Component                | Purpose              | Guidelines                                                                |
|--------------------------|----------------------|---------------------------------------------------------------------------|
| **Class Docstring**      | Shared preconditions | Setup common to all tests                                                 |
| **Brief Description**    | One-line summary     | Describe the ONE thing being verified; use `[NEGATIVE]` for failure tests |
| **Preconditions** (test) | Test-specific setup  | Only if this test has additional setup beyond the class                   |
| **Steps**                | Test action(s)       | Minimal - just what's needed to get the result to verify                  |
| **Expected**             | ONE assertion        | Use natural language that maps to assertions                              |
| **Parametrize**          | Matrix testing       | Optional - list parameter combinations                                    |
| **Markers**              | pytest markers       | Optional - list required decorators                                       |

---

## Best Practices

### Writing Effective STDs

1. **One Test = One Thing**: Each test should verify exactly one behavior.
   - Good: `test_ping_succeeds`, `test_ping_fails_when_isolated`
   - Bad: `test_ping_succeeds_and_fails_when_isolated`

2. **Group Related Tests in Classes**: Use class docstring for shared preconditions.
   - Good: Class `TestSnapshotRestore` with shared VM setup
   - Bad: Standalone functions with repeated preconditions

3. **Be Specific in Preconditions**: Describe the exact state required.
   - Good: `- File path="/data/original.txt", content="test-data"`
   - Bad: `- A file exists`

4. **No Fixture Names in Phase 1**: Fixtures are implementation details.
   - Good: `- Running Fedora virtual machine`
   - Bad: `- Running Fedora VM (vm_to_restart fixture)`

5. **Single Expected Behavior per Test**: One assertion: clear pass/fail.
   - Good: `Expected: - Ping succeeds with 0% packet loss`
   - Bad: `Expected: - Ping succeeds - VM remains running - No errors logged`
   - The may be **exceptions**, where multiple assertions are required to verify a **single** behavior.
     - Example: `Expected: - VM reports valid IP addres. Expected - User can access VM via SSH`

6. **Tests Must Be Independent**: Tests should not depend on other tests.
   - Dependencies between tests mean that one test depends on the result of a previous test.
   - If testing of a feature requires dependencies between tests, make sure that:
     - They are grouped under a class with shared preconditions
     - Use `@pytest.mark.incremental` marker to ensure tests dependency on previous test results
   - Good: Fixture `migrated_vm` sets up a VM that has been migrated
   - Bad: `test_migrate_vm` must run before `test_ssh_after_migration`

    Example:

    ```python
   import pytest

    @pytest.mark.incremental
    class TestVMSomeFeature:

        def test_vm_is_created(self):
            """
            Test that a VM with feature 1 can be created
            """

        def test_vm_migration(self):  # will be marked as xfailed if test_vm_is_created failed
            """
            Test that a VM with feature 1 can be migrated
            """

    ```

### Common Patterns in This Project

| Pattern                  | Description                               | Example                                       |
|--------------------------|-------------------------------------------|-----------------------------------------------|
| **Fixture-based Setup**  | Use pytest fixtures for resource creation | `vm_to_restart`, `namespace`                  |
| **Matrix Testing**       | Parameterize tests for multiple scenarios | `storage_class_matrix`, `run_strategy_matrix` |
| **Architecture Markers** | Indicate architecture compatibility       | `@pytest.mark.arm64`, `@pytest.mark.s390x`    |
| **Gating Tests**         | Critical tests for CI/CD pipelines        | `@pytest.mark.gating`                         |

### STD Checklist

#### Phase 1: Test Description PR

- [ ] STP link in module docstring
- [ ] Tests grouped in class with shared preconditions
- [ ] Each test has: description, Preconditions, Steps, Expected
- [ ] Each test verifies ONE thing with ONE Expected
- [ ] Negative tests marked with `[NEGATIVE]`
- [ ] Test methods/classes/tests contain only `__test__ = False`

#### Phase 2: Test Automation PR

- [ ] Implementation matches approved STD
- [ ] Fixtures implement preconditions
- [ ] Assertions match Expected
- [ ] No changes to STD docstrings

---

### Example 1: Group tests under a class

```python
"""
VM Snapshot and Restore Tests

STP Reference: https://example.com/stp/vm-snapshot-restore
"""

class TestSnapshotRestore:
    """
    Tests for VM snapshot restore functionality.

    Markers:
        - gating

    Preconditions:
        - Running VM with a data disk
        - File path="/data/original.txt", content="data-before-snapshot"
        - Snapshot created from VM
        - File path="/data/after.txt", content="post-snapshot" (written after snapshot)
        - VM Restored from snapshot, running and SSH accessible
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

    def test_removes_post_snapshot_file(self):
        """
        Test that files created after a snapshot are removed after restore.

        Steps:
            1. Check if file /data/after.txt exists on the restored VM

        Expected:
            - File /data/after.txt does NOT exist
        """
```


### Example 2: Tests with test-specific preconditions


```python
class TestVMLifecycle:
    """
    Tests for VM lifecycle operations.

    Preconditions:
        - VM Running latest Fedora virtual machine
    """
    __test__ = False

    def test_vm_restart_completes_successfully(self):
        """
        Test that a VM can be restarted.

        Steps:
            1. Restart the running VM and wait for completion

        Expected:
            - VM is "Running"
        """

    def test_vm_stop_completes_successfully(self):
        """
        Test that a VM can be stopped.

        Steps:
            1. Stop the running VM and wait for completion

        Expected:
            - VM is "Stopped"
        """

    def test_vm_start_after_stop(self):
        """
        Test that a stopped VM can be started.

        Preconditions:
            - VM is in stopped state

        Steps:
            1. Start the VM and wait for it to become running

        Expected:
            - VM is "Running" and SSH accessible
        """
```

---

### Example 3: Single Test (No Class Needed)

When a test stands alone without related tests, a class is not required:

```python
def test_flat_overlay_ping_between_vms():
    """
    Test that VMs on the same flat overlay network can communicate.

    Markers:
        - ipv4
        - gating

    Preconditions:
        - Flat overlay Network Attachment Definition created
        - VM-A running and attached to a flat overlay network
        - VM-B running and attached to a flat overlay network

    Steps:
        1. Get IPv4 address of VM-B
        2. Execute ping from VM-A to VM-B

    Expected:
        - Ping succeeds with 0% packet loss
    """

test_flat_overlay_ping_between_vms.__test__ = False
```

---

### Example 4: Negative Test

Tests that verify failure scenarios use the `[NEGATIVE]` indicator:

```python
def test_isolated_vms_cannot_communicate():
    """
    [NEGATIVE] Test that VMs on separate flat overlay networks cannot ping each other.

    Markers:
        - ipv4

    Preconditions:
        - NAD-1 flat overlay network created
        - NAD-2 separate flat overlay network created
        - VM-A running and attached to NAD-1
        - VM-B running and attached to NAD-2

    Steps:
        1. Get IPv4 address of VM-B
        2. Execute ping from VM-A to VM-B

    Expected:
        - Ping fails with 100% packet loss
    """

test_isolated_vms_cannot_communicate.__test__ = False
```

---

### Example 5: Parametrized Test

Tests that should run with multiple parameter combinations include a `Parametrize:` section:

```python
def test_online_disk_resize():
    """
    Test that a running VM's disk can be expanded.

    Markers:
        - gating

    Parametrize:
        - storage_class: [ocs-storagecluster-ceph-rbd, hostpath-csi]

    Preconditions:
        - Storage class from parameter exists
        - DataVolume with RHEL image using the storage class
        - Running VM with the DataVolume as boot disk

    Steps:
        1. Expand PVC by 1Gi
        2. Wait for resize to complete inside VM

    Expected:
        - Disk size inside VM is greater than original size
    """

test_online_disk_resize.__test__ = False
```

---
