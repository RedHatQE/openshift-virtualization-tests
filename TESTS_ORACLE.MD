# Test Oracle Instructions

<!-- Custom instructions for pr-test-oracle (https://github.com/myk-org/pr-test-oracle) -->
<!-- Integrated via github-webhook-server (https://github.com/myk-org/github-webhook-server) -->
<!-- Assisted-by: Claude <noreply@anthropic.com> -->

## Scope Rules

### Include Only Tests

Only recommend files under `tests/` that are actual test files (files starting with `test_` containing test functions/classes).
Do NOT recommend:
- Utility modules (`utils.py`, `helpers.py`)
- Conftest files (`conftest.py`) — these are fixtures, not runnable tests
- Constants files (`constants.py`)
- Any non-test Python file

If a conftest.py or utility file is modified, recommend the **tests that depend on it**, not the utility file itself.

### Exclude Unit Tests

Do NOT recommend tests under `utilities/unittests/`. These are unit tests for shared utilities and are covered by CI (`tox -e utilities-unittests`) automatically on every PR.

Focus exclusively on integration and end-to-end tests under `tests/`.

### Hardware and Architecture Awareness

This test suite runs on OpenShift clusters with varying hardware configurations. When recommending tests, consider:

- **SR-IOV tests** (`@pytest.mark.sriov`): Require SR-IOV capable NICs. Only recommend when changes affect SR-IOV fixtures, network policies, or SR-IOV-specific utilities.
- **GPU tests** (`@pytest.mark.gpu`): Require GPU hardware. Only recommend when changes affect GPU passthrough, vGPU, or GPU-related fixtures.
- **DPDK tests** (`@pytest.mark.dpdk`): Require DPDK-capable hardware. Only recommend when changes affect DPDK network configuration.
- **IBM bare metal** (`@pytest.mark.ibm_bare_metal`): Require specific IBM hardware. Only recommend when changes are IBM-specific.
- **Architecture-specific tests**: Tests may target specific CPU architectures (amd64, arm64, s390x). When changes are architecture-specific, note the required architecture in your recommendation.
- **Special infrastructure** (`@pytest.mark.special_infra`): Tests requiring non-standard cluster configurations.
- **High resource VMs** (`@pytest.mark.high_resource_vm`): Tests requiring VMs with large CPU/memory allocations.

When PR modifies fixtures for hardware-specific resources:
- **Collection safety**: Fixtures MUST have existence checks (return `None` when hardware unavailable).
- **Test plan**: MUST verify both WITH and WITHOUT hardware — run affected tests on cluster WITH hardware, and verify collection succeeds on cluster WITHOUT hardware.

### Prefer Marker-Based Recommendations

When possible, recommend a pytest marker (`-m marker_name`) that covers multiple related tests instead of listing individual test files. This is more efficient for test execution.

Common markers in this repository (check `pytest.ini` for the full list):
- `-m smoke` — Smoke tests (critical path validation)
- `-m sriov` — SR-IOV networking tests
- `-m gpu` — GPU passthrough tests
- `-m dpdk` — DPDK networking tests
- `-m sno` — Single-node OpenShift tests
- `-m ipv4` — IPv4 networking tests
- `-m single_stack` — Single-stack networking tests

If a change affects all tests with a specific marker, recommend `-m marker_name` instead of listing each test file individually.

When a marker covers ALL affected tests, use: `-m marker_name`
When a marker covers MOST but not all, use both: `-m marker_name` plus individual test paths for the uncovered ones.

### Smoke Test Impact Analysis

Determine if any changes could affect smoke tests by checking:
- Changes to files/functions used by tests marked with `@pytest.mark.smoke`
- Changes to fixtures or utilities imported by smoke tests
- Changes to conftest.py files that may affect smoke test execution
- Changes to core infrastructure code (`utilities/`, `libs/`) that smoke tests depend on

Before flagging smoke test impact, you MUST verify the dependency path:
- Trace the actual fixture dependency chain from smoke tests to changed fixtures
- Verify that smoke tests actually import/use changed utilities or functions
- Confirm the dependency path exists; do NOT assume based on scope or semantics
- Be conservative: session-scoped fixtures or infrastructure-sounding names do NOT automatically mean smoke test impact

WRONG: "This session-scoped storage fixture might affect smoke tests"
RIGHT: "Smoke test X uses fixture Y, which depends on the changed fixture Z"

## Analysis Approach

### For This Repository

This is a **test suite repository** — the changed files ARE often the tests themselves, or test infrastructure (fixtures, utilities, conftest files). Adapt analysis accordingly:

- If changed files are test files: recommend running those changed tests, plus any other tests that share fixtures, utilities, or base classes with them.
- If changed files are test utilities/fixtures/conftest: recommend running all tests that depend on or import from the changed utilities.
- If changed files are under `utilities/` or `libs/`: trace which tests import from these modules and recommend those tests.

### Dependency Tracing

1. Examine code changes in each modified file
2. Identify affected code paths, functions, and classes
3. Analyze pytest-specific elements: fixtures (scope, dependencies), parametrization, markers, conftest changes
4. Trace test dependencies through imports, shared utilities, and fixture inheritance
5. Detect new tests introduced in the PR
