# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Using a different AI tool?** See `AGENTS.md` for the tool-agnostic project rules.

@AGENTS.md

## Essential Commands

All commands use `uv run` - NEVER execute `python`, `pip`, `pytest`, `tox`, or `pre-commit` directly.

### Running Tests

```bash
# Basic test run
uv run pytest

# Run specific test
uv run pytest tests/storage/cbt/test_cbt.py::TestFullBackupRestore::test_full_backup_push_mode_restore

# Run tests by marker
uv run pytest -m network
uv run pytest -m "network and ipv4"

# Run tests by name pattern
uv run pytest -k "test_clone_windows_vm or test_migrate_vm"

# Skip cluster sanity checks (useful during development)
uv run pytest --cluster-sanity-skip-check
```

### Linting and Formatting

```bash
# Run all pre-commit checks (MANDATORY before committing)
uv run pre-commit run --all-files

# Run specific linter
uv run ruff check <file>
uv run ruff format <file>

# Full CI validation
uv run tox

# Run utilities unit tests
uv run tox -e utilities-unittests
```

### Environment Setup

Required environment variables before running tests:

```bash
# Bitwarden credentials
export ORGANIZATION_ID="<your-bitwarden-org-id>"
export ACCESS_TOKEN="<your-bitwarden-access-token>"

# Artifactory credentials
export ARTIFACTORY_USER=<your-username>
export ARTIFACTORY_TOKEN=<your-artifactory-token>
export ARTIFACTORY_SERVER=cnv-qe-artifactory.apps.int.prod-stable-spoke1-dc-rdu2.itup.redhat.com

# Cluster access
export KUBECONFIG=~/kubeconfig/<cluster-name>/auth/kubeconfig
```

### Package Management

```bash
# Update a specific package
uv lock --upgrade-package openshift-python-wrapper

# Update all packages
uv lock --upgrade

# Add a new dependency
uv add <package-name>
```

## Architecture Overview

### Directory Structure

- **`tests/`** — Test suites organized by component (network, storage, virt, infrastructure, data_protection, chaos, observability)
- **`utilities/`** — Shared utility functions for cluster operations, VM lifecycle, storage, and infrastructure
  - `cluster.py` — cluster-wide operations (oc commands, node operations)
  - `infra.py` — infrastructure helpers (SSH, networking, pod operations)
  - `virt.py` — VM lifecycle, VMI operations, migration helpers
  - `storage.py` — storage operations (PVC, DataVolume, StorageClass)
- **`libs/`** — Shared libraries with strict type checking (infra, net, storage, vm)
- **`ocp_resources/`** — Symlink to `openshift-python-wrapper/ocp_resources` for OpenShift resource classes
- **`containers/`** — Container image definitions for test utilities
- **`docs/`** — Documentation and test plans

### Key Concepts

**Test Organization:**
- Tests are organized by component under `tests/` (e.g., `tests/network/`, `tests/storage/`, `tests/virt/`)
- Each feature has its own subdirectory (e.g., `tests/network/ipv6/`, `tests/storage/cbt/`)
- Local helpers go in `<feature_dir>/utils.py`
- Local fixtures go in `<feature_dir>/conftest.py`
- Shared fixtures are in `tests/conftest.py`

**Markers:**
- Team markers (`network`, `storage`, `virt`, etc.) are added automatically based on directory location
- `tier2` is implicit for all tests without exclusion markers
- Tier semantics: tier1 = operator/infrastructure, tier2 = customer use cases, tier3 = complex/hardware-specific

**Matrix Fixtures:**
- Tests can run against multiple storage classes or configurations using matrix fixtures
- Format: `<type>_matrix__<scope>__` (e.g., `storage_class_matrix__module__`)
- Override via CLI: `--storage-class-matrix=ocs-storagecluster-ceph-rbd-virtualization,hostpath-csi-basic`

**Fixture Naming:**
- ALWAYS use nouns (what they provide): `vm_with_disk` ✅ not `create_vm_with_disk` ❌
- Return/yield the resource even for setup fixtures
- Scope: function (default), class, module, or session
- Session fixtures for expensive setup (storage class, namespace)

**Test Design Workflow:**
- New features require STP (Software Test Plan) → STD (Software Test Description with `__test__ = False`) → Implementation
- STD placeholders must be reviewed before implementation
- Each test verifies ONE aspect with ONE `Expected:` assertion

**Quarantine Mechanisms:**
- Product bugs: `@pytest.mark.jira("CNV-XXXXX", run=False)` (auto-re-enables when Jira resolves)
- Automation/investigation issues: `@pytest.mark.xfail(reason=f"{QUARANTINED}: ...", run=False)` (requires manual de-quarantine)

### Common Patterns

**Creating VMs:**
```python
from utilities.virt import VirtualMachineForTests, running_vm

with VirtualMachineForTests(
    name="test-vm",
    namespace=namespace.name,
    client=unprivileged_client,
    vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=U1_SMALL),
    vm_preference=VirtualMachineClusterPreference(client=client, name="rhel.9"),
    data_volume_template=...,
    os_flavor=OS_FLAVOR_RHEL,
) as vm:
    running_vm(vm=vm)
    # VM is ready for testing
```

**Waiting for Conditions:**
```python
from timeout_sampler import TimeoutSampler

for sample in TimeoutSampler(wait_timeout=60, sleep=5, func=check_condition):
    if sample:
        break
```

**SSH Commands to VMs:**
```python
from utilities.virt import run_ssh_commands
import shlex

result = run_ssh_commands(
    host=vm.ssh_exec,
    commands=shlex.split("cat /tmp/file.txt"),
    wait_timeout=TIMEOUT_2MIN,
    sleep=TIMEOUT_5SEC,
)
```

## Context-Specific Guidance

### Working with ocp-resources

Use `ocp-resources` classes for all Kubernetes/OpenShift resources — NEVER construct raw YAML dicts:

```python
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace
```

Resources support context managers and provide typed Python interfaces to K8s APIs.

### Working with Bitwarden Secrets

The test framework uses Bitwarden Secrets Manager for credentials. Secrets are cached automatically:
- `ACCESS_TOKEN` environment variable must be set
- Secrets are pulled via `utilities.bitwarden._run_bws_cli`

### Working with Artifactory

Internal images are hosted on Artifactory. Set these environment variables:
- `ARTIFACTORY_USER`, `ARTIFACTORY_TOKEN`, `ARTIFACTORY_SERVER`
- Or use `--skip-artifactory-check` to skip tests requiring internal images

### Cluster Architecture Detection

Tests dynamically select images based on cluster architecture (amd64, arm64, s390x):
- `utilities.architecture.get_cluster_architecture()` detects the cluster
- `utilities.constants.ArchImages` provides architecture-specific image URLs
- `utilities.constants.Images` auto-resolves to the correct architecture

### Jira Integration

Link tests to Jira tickets for automatic skip/xfail based on resolution status:

```python
# Skip test if Jira is not resolved
@pytest.mark.jira("CNV-1234", run=False)

# xfail test if Jira is not resolved
@pytest.mark.jira("CNV-1234")
```

Set environment variables: `PYTEST_JIRA_URL`, `PYTEST_JIRA_TOKEN`, `PYTEST_JIRA_USERNAME`
