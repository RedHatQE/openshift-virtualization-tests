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

This project follows a **two-phase development workflow** that separates test design from test implementation.

**Scope:** The traceability and STD lifecycle/format requirements in this guide apply only to product tests under `tests/`. Utilities unit tests under `utilities/unittests/` and tooling tests under `scripts/` are exempt; they require no STP/Jira traceability or STD docstring/lifecycle controls.

### Phase 1: Test Description PR (Design Phase)

1. **Create test stubs with docstrings only**:
   - Write the test function signature
   - Add the complete STD docstring (Preconditions/Steps/Expected)
   - Include the exact `STP: <URL>` link in **every test function or method docstring** when an STP exists. A module- or class-level link alone does not provide traceability for a new test.
   - When no STP exists, include the exact `Jira: <issue URL>  # <skip-jira-utils-check>` fallback in every test function or method docstring. Use Jira/RFE tracking links, not support cases.
   - Add applicable pytest markers (architecture markers, etc.) in the `Markers:` docstring section and keep those planned markers in the STD during Phase 1. Add the real `@pytest.mark.manual` decorator directly to every docstring-only test.
   - Add effective `__test__ = False` to every unimplemented test: use module/class scope where it applies, and `<test_name>.__test__ = False` for a standalone test. `@pytest.mark.manual` classifies the placeholder but does not suppress collection.

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
   - Remove both the direct `@pytest.mark.manual` decorator and `__test__ = False` from implemented tests; manual classification is only for unautomated/docstring-only tests.
   - When automating only part of a class/module, move `__test__ = False` onto each remaining placeholder (`<test_name>.__test__ = False`) before removing the shared assignment. Keep their direct manual decorators so only implemented tests become collectable.
   - Retain the direct `STP: <URL>` or `Jira: <issue URL>` traceability line in each test docstring.
   - Convert `Markers:` entries from STD docstrings to real pytest expressions:
     - Module-level markers → `pytestmark = [pytest.mark.<marker>]` at module scope
     - Class-level markers → `@pytest.mark.<marker>` on the class
     - Test-level markers → `@pytest.mark.<marker>` on the test function
     - `pytestmark` is a **Phase 2 addition** — it is intentionally absent from STD placeholders
   - If needed, update the test description. This change must be approved by the team's qe sig owner / lead.

2. **Submit PR for review**:
   - Reviewers verify the implementation matches the approved design
   - Focus is on code quality, correctness, and adherence to the STD

3. **Approval, verification and merge**:
   - Once implementation is verified, merge the automation

### Per-Test Traceability

Traceability belongs to the test that covers the scenario. Every new product test function or method under `tests/` must contain one of these exact labels in its own docstring:

```text
STP: https://example.com/stp/<scenario>
```

If no STP exists, use a Jira or RFE link instead (never a support case), with the required same-line `# <skip-jira-utils-check>` suffix. The URL below is illustrative; replace it with the applicable issue:

```text
Jira: https://issues.redhat.com/browse/CNV-1234  # <skip-jira-utils-check>
```

A module- or class-level link may document shared context, but it does not replace the direct link in each test docstring. Historical traceability must be retained when tests are modified or deleted; follow the repository's existing retention and deletion rules.

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

Docstring-only STD tests are not automation and must not be collected. Use `__test__ = False` at the module or class level, or on each standalone test function. Add the real manual marker separately: it classifies the test and does not suppress collection.

```python
"""Illustrative module containing only STD placeholder tests."""

import pytest

__test__ = False

@pytest.mark.manual
def test_abc():
    """
    Test that the example behavior is documented before automation.

    STP: https://example.com/stp/example-behavior

    Preconditions:
        - Example system is available

    Steps:
        1. Perform the example action manually

    Expected:
        - Example behavior succeeds
    """
```

For a class of STD methods, set `__test__ = False` on the class and put the direct manual decorator and traceability link on every method:

```python
import pytest

class TestClass:
    __test__ = False

    @pytest.mark.manual
    def test_abc(self):
        """
        Test that the example behavior is documented before automation.

        STP: https://example.com/stp/example-behavior

        Preconditions:
            - Example system is available

        Steps:
            1. Perform the example action manually

        Expected:
            - Example behavior succeeds
        """
```

### Negative Test Indicator

Mark tests that verify failure scenarios with `[NEGATIVE]` in the description:

```python
import pytest

@pytest.mark.manual
def test_isolated_vms_cannot_communicate():
    """
    [NEGATIVE] Test that VMs on separate networks cannot ping each other.

    STP: https://example.com/stp/isolated-network

    Preconditions:
        - Client VM and server VM are on separate networks

    Steps:
        1. Ping the server VM from the client VM

    Expected:
        - Ping fails
    """

test_isolated_vms_cannot_communicate.__test__ = False
```

### Parametrization Hints

When a test should run with multiple parameter combinations, add a `Parametrize:` section.

Parameter values may have their own markers using inline `[Markers: ...]` syntax to differentiate between common test markers and parameter-specific ones:

```text
Parametrize:
    - ip_family:
        - ipv4 [Markers: ipv4]
        - ipv6 [Markers: ipv6]
```

### Markers Section

When specific pytest markers are required, list them explicitly in `Markers:`. During Phase 1, planned markers other than `manual` remain documentation entries and are converted during Phase 2. The real `@pytest.mark.manual` decorator is required directly on each unautomated/docstring-only test. Markers can be described at any level:
- **Module docstring** — markers that apply to all tests in the module
- **Class docstring** — markers that apply to all tests in the class
- **Test docstring** — markers specific to a single test

---

## STD Template

**Key Principles:**
- Each test should verify **ONE thing**
- **Tests must be independent** - no test should depend on another test's outcome
- Related tests are grouped in a **test class**
  - If a test needs a precondition that could be another test's outcome, place the tests under the class in the required order
  - Mention handling of early failures (i.e "fail fast")
- **Shared preconditions** go in the class/module docstring
- **Test-specific preconditions** (if any) go in the test docstring
- **Shared resources used directly by tests** must be mentioned at both levels: in the shared preconditions (class/module) AND in the test-level preconditions. E.g., a VM shared across the module and used in tests should appear in both the module/class preconditions and each test's preconditions.
- **Per-test traceability** must be direct: each test function/method docstring contains `STP: <URL>` when an STP exists, or `Jira: <issue URL>` when no STP exists. Module/class-only links do not satisfy this requirement.

### Class-Level Template

```python
import pytest

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

    @pytest.mark.manual
    def test_<specific_behavior>(self):
        """
        Test that <specific ONE thing being verified>.

        STP: https://example.com/stp/<scenario>

        Steps:
            1. <The test action to perform>

        Expected:
            - <Natural language assertion, e.g., "VM is Running", "File exists">
        """
```

### Test-Level Template

For standalone tests without related tests:

```python
import pytest

@pytest.mark.manual
def test_<specific_behavior>():
    """
    Test that <specific ONE thing being verified>.

    STP: https://example.com/stp/<scenario>

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
| **Traceability**         | Per-test tracking    | Exact `STP: <URL>` or `Jira: <issue URL>` in every test docstring         |
| **Markers**              | pytest markers       | List planned decorators; use direct `@pytest.mark.manual` in Phase 1      |

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

5. **Name Resources by Function**: Name objects by their role, not generic labels.
   - Good: `- Connectivity reference VM`, `- Client VM`
   - Bad: `- VM-A`, `- VM-B`, `- First VM`
   - This is especially important when multiple resources of the same kind are used, to clarify each resource's purpose.

6. **Single Expected Behavior per Test**: One assertion: clear pass/fail.
   - Good: `Expected: - Ping succeeds with 0% packet loss`
   - Bad: `Expected: - Ping succeeds - VM remains running - No errors logged`
   - There may be **exceptions**, where multiple assertions are required to verify a **single** behavior.
     - Example: `Expected: - VM reports valid IP addres. Expected - User can access VM via SSH`

7. **Tests Must Be Independent**: Tests should not depend on other tests.
   - Dependencies between tests mean that one test depends on the result of a previous test.
   - If testing of a feature requires dependencies between tests, make sure that:
     - They are grouped under a class with shared preconditions
     - List `incremental` in the class `Markers:` section during Phase 1; apply `@pytest.mark.incremental` during Phase 2 to preserve the dependency on previous test results
   - Good: Fixture `migrated_vm` sets up a VM that has been migrated
   - Bad: `test_migrate_vm` must run before `test_ssh_after_migration`

    Example:

    ```python
    import pytest

    class TestVMSomeFeature:
        """
        Markers:
            - incremental
        """
        __test__ = False

        @pytest.mark.manual
        def test_vm_is_created(self):
            """
            Test that a VM with feature 1 can be created.

            STP: https://example.com/stp/vm-feature-1

            Preconditions:
                - Feature 1 is available

            Steps:
                1. Create a VM with feature 1

            Expected:
                - The VM is created
            """

        @pytest.mark.manual
        def test_vm_migration(self):
            """
            Test that a VM with feature 1 can be migrated.

            STP: https://example.com/stp/vm-feature-1

            Preconditions:
                - A VM with feature 1 is running

            Steps:
                1. Migrate the VM

            Expected:
                - The VM remains running after migration
            """

    ```

### Common Patterns in This Project

| Pattern                  | Description                                          | Example                                                      |
|--------------------------|------------------------------------------------------|--------------------------------------------------------------|
| **Fixture-based Setup**  | Use pytest fixtures for resource creation            | `vm_to_restart`, `namespace`                                 |
| **Parameterize Testing** | Parametrize tests or fixtures for multiple scenarios | `@pytest.mark.parametrize("run_strategy", [Always, Manual])` |
| **Matrix Testing**       | Advanced parametrization via dynamic fixtures        | `storage_class_matrix`, `run_strategy_matrix`                |
| **Architecture Markers** | Indicate architecture compatibility                  | `@pytest.mark.arm64`, `@pytest.mark.s390x`                   |
| **Gating Tests**         | Critical tests for CI/CD pipelines                   | `@pytest.mark.gating`                                        |

### STD Checklist

#### Phase 1: Test Description PR

- [ ] Every test function/method docstring has exact `STP: <URL>`, or `Jira: <issue URL>` when no STP exists
- [ ] Tests grouped in class with shared preconditions where appropriate
- [ ] Each test has: description, traceability line, Preconditions, Steps, Expected
- [ ] Each test verifies ONE thing with ONE Expected
- [ ] Negative tests marked with `[NEGATIVE]`
- [ ] Every docstring-only test has direct `@pytest.mark.manual` and effective `__test__ = False`
- [ ] Jira fallback lines have the same-line `# <skip-jira-utils-check>` suffix; no support-case links

#### Phase 2: Test Automation PR

- [ ] Implementation matches approved STD
- [ ] Fixtures implement preconditions
- [ ] Assertions match Expected
- [ ] No changes to approved STD docstrings, including per-test traceability
- [ ] Remove both direct `@pytest.mark.manual` and `__test__ = False` when automation is added
- [ ] `Markers:` entries from STD docstrings converted to `pytestmark` or `@pytest.mark` decorators

---

### Example 1: Group tests under a class

```python
"""
VM Snapshot and Restore Tests

Shared preconditions for this class are documented here; each test retains its own traceability.
"""

import pytest

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

    @pytest.mark.manual
    def test_preserves_original_file(self):
        """
        Test that files created before a snapshot are preserved after restore.

        STP: https://example.com/stp/vm-snapshot-restore

        Preconditions:
            - Data disk attached to the VM
            - Running VM with /data/original.txt preserved from before the snapshot
            - VM restored from the snapshot and SSH accessible

        Steps:
            1. Read file /data/original.txt from the restored VM

        Expected:
            - File content equals "data-before-snapshot"
        """

    @pytest.mark.manual
    def test_removes_post_snapshot_file(self):
        """
        Test that files created after a snapshot are removed after restore.

        STP: https://example.com/stp/vm-snapshot-restore

        Preconditions:
            - Data disk attached to the VM
            - Running VM with /data/after.txt created after the snapshot
            - VM restored from the snapshot and SSH accessible

        Steps:
            1. Check if file /data/after.txt exists on the restored VM

        Expected:
            - File /data/after.txt does NOT exist
        """
```


### Example 2: Tests with test-specific preconditions


```python
import pytest

class TestVMLifecycle:
    """
    Tests for VM lifecycle operations.

    Preconditions:
        - VM running the latest Fedora image
    """
    __test__ = False

    @pytest.mark.manual
    def test_vm_restart_completes_successfully(self):
        """
        Test that a VM can be restarted.

        STP: https://example.com/stp/vm-lifecycle

        Preconditions:
            - VM running the latest Fedora image

        Steps:
            1. Restart the running VM and wait for completion

        Expected:
            - VM is "Running"
        """

    @pytest.mark.manual
    def test_vm_stop_completes_successfully(self):
        """
        Test that a VM can be stopped.

        STP: https://example.com/stp/vm-lifecycle

        Preconditions:
            - VM running the latest Fedora image

        Steps:
            1. Stop the running VM and wait for completion

        Expected:
            - VM is "Stopped"
        """

    @pytest.mark.manual
    def test_vm_start_after_stop(self):
        """
        Test that a stopped VM can be started.

        STP: https://example.com/stp/vm-lifecycle

        Preconditions:
            - VM created from the latest Fedora image is stopped

        Steps:
            1. Start the VM and wait for it to become running

        Expected:
            - VM is "Running" and SSH accessible
        """
```

---

### Jira Fallback Example

When a new test has no STP, use the Jira or RFE issue URL directly in the test docstring with the same-line `# <skip-jira-utils-check>` suffix. Do not use a support-case URL. Replace the illustrative URL below with the applicable issue.

```python
import pytest

@pytest.mark.manual
def test_feature_behavior_without_stp():
    """
    Test the behavior tracked by the fallback Jira issue.

    Jira: https://issues.redhat.com/browse/CNV-1234  # <skip-jira-utils-check>

    Preconditions:
        - The feature is available in the test environment

    Steps:
        1. Exercise the feature

    Expected:
        - The feature behaves as described by the issue
    """

test_feature_behavior_without_stp.__test__ = False
```

---

### Example 3: Single Test (No Class Needed)

When a test stands alone without related tests, a class is not required:

```python
import pytest

@pytest.mark.manual
def test_flat_overlay_ping_between_vms():
    """
    Test that VMs on the same flat overlay network can communicate.

    STP: https://example.com/stp/vm-flat-overlay

    Markers:
        - ipv4
        - gating

    Preconditions:
        - Flat overlay Network Attachment Definition created
        - Client VM running and attached to a flat overlay network
        - Server VM running and attached to a flat overlay network

    Steps:
        1. Get the IPv4 address of the server VM
        2. Execute ping from the client VM to the server VM

    Expected:
        - Ping succeeds with 0% packet loss
    """

test_flat_overlay_ping_between_vms.__test__ = False
```

---

### Example 4: Negative Test

Tests that verify failure scenarios use the `[NEGATIVE]` indicator:

```python
import pytest

@pytest.mark.manual
def test_isolated_vms_cannot_communicate():
    """
    [NEGATIVE] Test that VMs on separate flat overlay networks cannot ping each other.

    STP: https://example.com/stp/vm-isolated-overlay

    Markers:
        - ipv4

    Preconditions:
        - Client flat overlay network created
        - Server flat overlay network created separately from the client network
        - Client VM running and attached to the client network
        - Server VM running and attached to the server network

    Steps:
        1. Get the IPv4 address of the server VM
        2. Execute ping from the client VM to the server VM

    Expected:
        - Ping fails with 100% packet loss
    """

test_isolated_vms_cannot_communicate.__test__ = False
```

---

### Example 5: Parametrized Test

Tests that should run with multiple parameter combinations include a `Parametrize:` section:

```python
import pytest

@pytest.mark.manual
def test_online_disk_resize():
    """
    Test that a running VM's disk can be expanded.

    STP: https://example.com/stp/online-disk-resize

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

### Example 6: Module-Level Preconditions

When a module contains multiple classes or standalone tests that share common setup, use the **module docstring** for shared preconditions. Resources used directly by tests must appear in both the module preconditions and the test-level preconditions:

```python
"""
VM Live Migration Tests

Markers:
    - gating

Preconditions:
    - Two worker nodes available for migration
    - Running VM with the latest Fedora image, accessible via SSH

"""

import pytest

__test__ = False

@pytest.mark.manual
def test_ssh_connectivity_after_migration():
    """
    Test that SSH connectivity is preserved after live migration.

    STP: https://example.com/stp/vm-live-migration

    Preconditions:
        - Two worker nodes available for migration
        - Running VM with the latest Fedora image, accessible via SSH

    Steps:
        1. Live migrate the VM to another node
        2. Wait for migration to complete
        3. Connect to VM via SSH

    Expected:
        - SSH connection succeeds
    """

@pytest.mark.manual
def test_data_disk_accessible_after_migration():
    """
    Test that data disk content is preserved after live migration.

    STP: https://example.com/stp/vm-live-migration

    Preconditions:
        - Two worker nodes available for migration
        - Running VM with the latest Fedora image, accessible via SSH
        - Data disk attached to the VM with test data written to a file

    Steps:
        1. Live migrate the VM to another node
        2. Read data from the data disk

    Expected:
        - Data disk content equals the written test data
    """

```

---
