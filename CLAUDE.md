# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strict Rules (MANDATORY)
Based on https://github.com/myk-org/github-metrics/blob/main/CLAUDE.md#strict-rules-mandatory

### Linter Suppressions PROHIBITED

- ❌ **NEVER** add `# noqa`, `# type: ignore`, `# pylint: disable`
- ❌ **NEVER** disable linter/mypy rules to work around issues
- ✅ **FIX THE CODE** - If linter complains, the code is wrong
- If you think a rule is wrong: **ASK** the user for explicit approval

### Code Reuse (Search-First Development)

Before writing ANY new code:

1. **SEARCH** codebase for existing implementations
2. **CHECK** `utilities/` for shared functions
3. **CHECK** `libs/` for shared libraries
4. **CHECK** `tests/` for shared fixtures and helper functions
5. **VERIFY** no similar logic exists elsewhere
6. **NEVER** duplicate logic - extract to shared module

| Logic Type                           | Location                                                        |
|--------------------------------------|-----------------------------------------------------------------|
| Infrastructure/cluster utilities     | `utilities/infra.py`                                            |
| Network utilities                    | `utilities/network.py`                                          |
| Storage utilities                    | `utilities/storage.py`                                          |
| Virtualization utilities             | `utilities/virt.py`                                             |
| Constants and enums                  | `utilities/constants.py`                                        |
| HCO/operator management              | `utilities/hco.py`, `utilities/operator.py`                     |
| CPU/NUMA utilities                   | `utilities/cpu.py`                                              |
| OS/guest utilities                   | `utilities/os_utils.py`, `utilities/guest_support.py`           |
| SSP (scheduling, scale, performance) | `utilities/ssp.py`                                              |
| Monitoring/metrics                   | `utilities/monitoring.py`                                       |
| Data collection/must-gather          | `utilities/data_collector.py`, `utilities/must_gather.py`       |
| Bitwarden/secrets                    | `utilities/bitwarden.py`                                        |
| Exceptions                           | `utilities/exceptions.py`                                       |
| Pytest helpers                       | `utilities/pytest_utils.py`, `utilities/pytest_matrix_utils.py` |
| Logging setup                        | `utilities/logger.py`                                           |
| OADP (backup/restore)                | `utilities/oadp.py`                                             |
| Cluster sanity checks                | `utilities/sanity.py`                                           |
| VNC utilities                        | `utilities/vnc_utils.py`                                        |
| Database utilities                   | `utilities/database.py`                                         |
| Jira integration                     | `utilities/jira.py`                                             |
| Console utilities                    | `utilities/console.py`                                          |
| Data manipulation                    | `utilities/data_utils.py`                                       |
| Artifactory utilities                | `utilities/artifactory.py`                                      |
| Architecture detection               | `utilities/architecture.py`                                     |
| Network libs (typed)                 | `libs/net/`                                                     |
| Storage libs (typed)                 | `libs/storage/`                                                 |
| VM libs (typed)                      | `libs/vm/`                                                      |
| Infrastructure libs (typed)          | `libs/infra/`                                                   |
| Shared test fixtures                 | `tests/conftest.py`                                             |

### Python Requirements

- **Type hints MANDATORY** - mypy strict mode in `libs/`, all new public functions under utilities must be typed
- **Google-format docstrings** - for all public functions that are not self-explanatory
- **No defensive programming** - fail-fast, don't hide bugs with fake defaults
- **Always use `uv run`** - NEVER execute `python` or `pip` directly
- **Use absolute imports** - never relative imports
- **Import specific functions** - prefer `from module import func` over `import module`
- **Use named arguments** - call functions with argument names for clarity
- **Use caching** - use `@functools.cache` to reduce unnecessary calls
- **No single-letter variable names** - use descriptive, meaningful names
- **No dead code** - every function, variable, fixture MUST be used or removed. Only code marked with `# skip-unused-code` can be ignored.
- **Don't save attributes to variables** - use `foo.attr` directly, not `x = foo.attr; use(x)`

### Test Requirements

- **Fixtures do ONE action only** - single responsibility
- **Fixture names are NOUNS** - describe what they provide, not what they do
- **NO imports from conftest.py** - fixtures only, no utility functions
- **All new tests need markers** - check pytest.ini for available markers
- **Each test verifies ONE aspect** - single purpose, easy to understand
- **Tests should be independent** - use `pytest-dependency` only when necessary. Propose alternatives if possible.
- **Use appropriate fixture scopes** - broader scopes (class, module, session) reduce execution time but create shared state; use only for read-only resources or expensive setup where isolation isn't compromised
- **Use `@pytest.mark.usefixtures`** - when fixture return value is not needed

### Logging Guidelines

- **Log enough to debug** - but don't spam with unhelpful info
- **Error logs must be detailed** - include what failed, status, context
- **Use appropriate log levels** - DEBUG for verbose, INFO for general, ERROR for failures

### Directory Organization

- **Feature subdirectories** - each feature gets its own subdirectory under component
- **Test file naming** - use `test_<functionality>.py`
- **Local helpers** - place helper utils in the test's subdirectory
- **Local fixtures** - place in `conftest.py` under the test's subdirectory
- **Keep code close to usage** - move to shared location only when needed by multiple modules

## Project Overview

**openshift-virtualization-tests** - Test suite for OpenShift Virtualization (CNV - Container Native Virtualization)

- **Python**: 3.14+
- **Test Framework**: pytest 9.0+
- **Package Manager**: uv (NEVER use `pip` or `python` directly)

## Essential Commands

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test by name pattern
uv run pytest -k "test_clone_windows_vm or test_migrate_vm"

# Run tests by marker
uv run pytest -m network
uv run pytest -m smoke
uv run pytest -m "network and ipv4"

# Run conformance tests (requires storage class)
uv run pytest -m conformance --conformance-storage-class=<storage-class-name> --skip-artifactory-check

# Run chaos tests
uv run pytest -m chaos

# Custom config file
uv run pytest -c custom-pytest.ini
uv run pytest --tc-file=tests/global_config_aws.py
```

### Development

```bash
# Install/sync dependencies
uv sync

# Update packages
uv lock --upgrade
uv lock --upgrade-package openshift-python-wrapper

# Run pre-commit checks
pre-commit run --all-files

# Run CI checks
tox

# Run utilities unit tests (REQUIRES 95% coverage)
uv run --extra utilities-test pytest utilities/unittests/
```

## Code Architecture

### Directory Structure

```
tests/                          # Test suites organized by team/component
├── network/                    # Network component tests
├── storage/                    # Storage tests
├── virt/                       # Virtualization tests
├── chaos/                      # Chaos/reliability tests
├── infrastructure/             # Infrastructure tests
├── observability/              # Metrics and alerts tests
├── install_upgrade_operators/  # Install/upgrade tests
├── data_protection/            # Data protection tests
├── scale/                      # Scale tests
├── conftest.py                 # Shared test fixtures across teams
└── global_config*.py           # Test configuration for different platforms

utilities/                      # Project-wide utility functions
├── infra.py                    # Infrastructure/cluster utilities
├── network.py                  # Network utilities
├── storage.py                  # Storage utilities
├── virt.py                     # Virtualization utilities
├── constants.py                # Project constants
└── unittests/                  # Unit tests (MUST maintain 95% coverage)

libs/                           # Shared libraries (strict mypy typing enforced)

conftest.py                     # Root: pytest native fixtures and CLI options
```

### Key External Dependencies

- `openshift-python-wrapper` - Kubernetes/OpenShift API interactions
- `pytest-testconfig` - Test configuration via `--tc-file`
- `pytest-dependency` - Test dependencies
- `pytest-order` - Test ordering

## Important Test Markers

Most commonly used markers from pytest.ini:

- `smoke` - Smoke tests
- `conformance` - Standard cluster tests
- `network`, `storage`, `virt`, `chaos`, `infrastructure`, `observability`, `install_upgrade_operators` - Team-specific tests
- `destructive` - Destructive tests
- `sno` - Single Node OpenShift tests
- `ipv4`, `ipv6` - IP version specific
- `arm64`, `x86_64`, `s390x` - Architecture specific
- `sriov`, `gpu`, `special_infra` - Hardware requirements

## Code Style Rules

- **Style Guide**: Google Python Style Guide
- **Docstrings**: Google-format
- **Type Hints**: MANDATORY, enforced via mypy (especially in `libs/`)
- **Line Length**: 120 characters
- **Linting**: Ruff

## Fixture Guidelines (CRITICAL)

1. **Single Action**: Fixtures should do ONE action only
2. **Naming**: Use nouns (what they provide), NOT verbs
   - ✅ `vm_with_disk`
   - ❌ `create_vm_with_disk`
3. **Parametrization**: Use `request.param` with dict structure
4. **Ordering**: pytest native fixtures first, then session-scoped, then others
5. **NO IMPORTS**: Do NOT import from conftest.py files - fixtures only

## PR Process

- PRs reviewed by CodeRabbit
- Requires "verified" label
- Requires 2 reviewers + 1 approver from OWNERS file
- Use `/lgtm` and `/approve` comments
- CI must pass (tox checks)

## CodeRabbit Integration

This repository uses [CodeRabbit](https://coderabbit.ai/) for automated PR reviews. CodeRabbit analyzes code changes and provides review comments.

### Interacting with CodeRabbit

Use these commands in PR comments:

| Command | Description |
|---------|-------------|
| `@coderabbitai review` | Request a new review |
| `@coderabbitai resolve` | Mark all conversations resolved |
| `@coderabbitai pause` | Pause reviews on this PR |
| `@coderabbitai resume` | Resume reviews on this PR |

### Smoke Tests Automation

CodeRabbit integrates with the smoke tests workflow:

1. When a PR gets the `verified` label, a workflow requests CodeRabbit to analyze the changes
2. CodeRabbit posts a **Test Execution Plan** with `**Run smoke tests: True/False**`
3. If `True`, the `smoke-tests:pending-analysis` label is automatically added to the PR
4. This label can block merge until smoke tests are addressed

**Test Execution Plan Format** (posted by CodeRabbit):
```
## Test Execution Plan

**Run smoke tests: True**

### Tests Required:
- `-m smoke` - Run smoke test suite
- `path/to/test_file.py::test_name` - Specific tests
```

### Addressing CodeRabbit Comments

- All CodeRabbit review comments MUST be addressed before merge
- Use 👍 reaction or reply "done" when a comment is resolved
- CodeRabbit will re-review when new commits are pushed

## Prerequisites for Testing

- OpenShift cluster with CNV installed
- `oc` and `virtctl` binaries from cluster's consoleCliDownloads
- `bws` (Bitwarden CLI) for secrets
- KUBECONFIG set or logged in via `oc login`

## Critical Notes

- **ALWAYS use `uv run`**: Never execute `python` or `pytest` directly
- **Utilities Coverage**: 95% coverage is MANDATORY for utilities/unittests/
- **Type Safety**: mypy strict mode in libs/ - all code must be typed
- **Fixture Isolation**: Each fixture should be self-contained and reusable
- **Config Files**: Use `--tc-file` for platform-specific configurations
