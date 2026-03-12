# Test Oracle Instructions

<!-- Custom instructions for pr-test-oracle (https://github.com/myk-org/pr-test-oracle) -->
<!-- Integrated via github-webhook-server (https://github.com/myk-org/github-webhook-server) -->
<!-- Assisted-by: Claude <noreply@anthropic.com> -->

## Analysis Approach

This is a **test suite repository** — the changed files ARE often the tests themselves, or test infrastructure (fixtures, utilities, conftest files). Adapt analysis accordingly:

1. Examine code changes in each modified file
2. Identify affected code paths, functions, and classes
3. Analyze pytest-specific elements: fixtures (scope, dependencies), parametrization, markers, conftest changes
4. Trace test dependencies through imports, shared utilities, and fixture inheritance
5. Detect new tests introduced in the PR

## Scope Rules

YOU MUST ONLY recommend files under `tests/` that are actual test files (files starting with `test_`).
YOU MUST IGNORE tests under `utilities/unittests/`!
Do NOT recommend:
- Utility modules (`utils.py`, `helpers.py`)
- Conftest files (`conftest.py`) — these are fixtures, not runnable tests
- Constants files (`constants.py`)
- Any non-test Python file

If a conftest.py or utility file is modified, recommend the **tests that depend on it**, not the utility file itself.

### Hardware and Architecture Awareness

This test suite runs on OpenShift clusters with varying hardware configurations. When recommending tests, consider:

- **SR-IOV tests** (`@pytest.mark.sriov`): Require SR-IOV capable NICs. Only recommend when changes affect SR-IOV fixtures, network policies, or SR-IOV-specific utilities.
- **GPU tests** (`@pytest.mark.gpu`): Require GPU hardware. Only recommend when changes affect GPU passthrough, vGPU, or GPU-related fixtures.
- **DPDK tests** (`@pytest.mark.dpdk`): Require DPDK-capable hardware. Only recommend when changes affect DPDK network configuration.
- **IBM bare metal** (`@pytest.mark.ibm_bare_metal`): Require specific IBM hardware. Only recommend when changes are IBM-specific.
- **Architecture-specific tests**: Tests may target specific CPU architectures (amd64, arm64, s390x). When changes are architecture-specific, note the required architecture in your recommendation.
- **Special infrastructure** (`@pytest.mark.special_infra`): Tests requiring non-standard cluster configurations.post_upgrade
- **High resource VMs** (`@pytest.mark.high_resource_vm`): Tests requiring VMs with large CPU/memory allocations.

When PR modifies fixtures for hardware-specific resources:
- **Collection safety**: Fixtures MUST have existence checks (return `None` when hardware unavailable).
- **Test plan**: MUST verify both WITH and WITHOUT hardware — run affected tests on cluster WITH hardware, and verify collection succeeds on cluster WITHOUT hardware.

### Smoke Test Impact Analysis

The repository contains scripts/tests_analyzer/pytest_marker_analyzer.py - run it with `--output json -m smoke`
Output format is: - **Run smoke tests: True / False** (you must use the script output json, section `should_run_tests`). Reason: ((you must use the script output json, section `reason`)

### Pytest Execution Command

You MUST include a pytest execution command which contains ALL recommended tests.
Include path to specific tests (test_file::test_xx for example), and not files, if only specific tests in test file were modified.
ALWAYS check if a pytest marker (`-m marker_name`) that covers multiple related tests instead of listing individual tests can be used.
This is more efficient for test execution.
Check `pytest.ini` for the full list of supported markers.
When a marker covers ALL affected tests, use: `-m marker_name`
When a marker covers MOST but not all, use both: `-m marker_name` plus additional tests for the uncovered ones.
Output format is: - **pytest execution command**: `uv run pytest <the execution command>`
