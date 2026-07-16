# Code Organization

Where shared constants, utility functions, and pytest fixtures belong, and how to import them.

For general coding style see [CODING_AND_STYLE_GUIDE.md](CODING_AND_STYLE_GUIDE.md). For enforceable
AI/review rules see [AGENTS.md](../AGENTS.md).

## Shared principles

- **Thematic modules** — one concern per file; no catch-all modules.
- **Search first** — before adding anything, check existing `utilities/`, `libs/`, and `tests/` code.
- **Absolute imports** — always `from utilities.… import …`, never relative imports.
- **Submodule imports** — import from the specific module that owns the symbol; do not rely on
  package-level re-exports except where documented below.
- **No helpers in conftest** — `conftest.py` and `test_*.py` contain fixtures and tests only;
  helpers belong in `utilities/`, `libs/`, or feature `utils.py` files.

---

## Constants (`utilities/constants/`)

Test and utility code shares string literals, timeouts, resource names, and configuration values
through the `utilities/constants/` package. Each file is a thematic submodule.

### Import policy

```python
# Preferred — import from the owning submodule
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.constants.cluster import KUBERNETES_ARCH_LABEL

# Exception — Images only (computed at package import time; see below)
from utilities.constants import Images
```

- Do **not** use `from utilities.constants import X` for any name other than `Images`.
- Do **not** add re-exports to `utilities/constants/__init__.py` (except `Images`).

### Adding a new constant

1. Read submodule docstrings (`Covers` / `Not here` sections) to pick the right file.
2. Add the constant there; update the module docstring if the scope changes.
3. Submodule files must **not** import from other `utilities/constants/` submodules — only from
   `libs/`, `ocp_resources`, or the standard library.
4. Import the constant at call sites from the submodule directly.
5. Keep single-use values local to the test or feature module instead of adding them to the package.

### `Images` exception

`Images` is resolved in `utilities/constants/__init__.py` based on cluster architecture.
This avoids a circular import between `utilities/architecture.py` and the constants package.
Use `from utilities.constants import Images` only for this alias. For `ArchImages`, OS flavor
strings, and other image constants, import from `utilities/constants/images.py`.

Architecture-specific image setup is described in [ARCHITECTURE_SUPPORT.md](ARCHITECTURE_SUPPORT.md).

### Module map

| Submodule | Use for |
| --- | --- |
| `aaq.py` | Application-Aware Quota resource names, quota field keys, namespace labels, quota spec dicts |
| `architecture.py` | CPU architecture strings (`AMD_64`, `ARM_64`, …), vendor identifiers, supported architecture sets |
| `cluster.py` | Kubernetes node labels, `NODE_STR`, API verb strings, env vars, pod security labels, audit-log commands |
| `components.py` | CNV operator/pod/deployment/service **name strings** and Kubernetes kind strings (`kubectl get <kind>/<name>`) |
| `cpu_models.py` | CPU model exclusion lists for guest compatibility |
| `hco.py` | HCO status conditions, upgrade streams, TLS profiles, feature gate keys, CNV CRD list |
| `images.py` | `ArchImages`, OS flavor strings, image disk names, `DEFAULT_FEDORA_REGISTRY_URL` |
| `instance_types.py` | Instance type and VM preference name strings (`U1_*`, `RHEL*_PREFERENCE`, `WINDOWS_*_PREFERENCE`) |
| `monitoring.py` | Alert severities, operator health metrics, KubeVirt VMI metric names, Prometheus service name |
| `namespaces.py` | `NamespacesNames` — well-known OpenShift and CNV namespace strings |
| `networking.py` | SR-IOV, bridge types, ports, KubeMacPool config, bonding, network test pod specs |
| `oadp.py` | OADP test file names, backup storage location names |
| `os_matrix.py` | Common-templates test matrix **parameter keys** (`IMAGE_NAME_STR`, `DV_SIZE_STR`, …) |
| `pytest.py` | Pytest exit codes, quarantine strings, fixture scope strings, unprivileged test credentials |
| `storage.py` | `StorageClassNames`, CDI/HPP labels, hotplug constants, DataVolume source types, DataImportCron values |
| `tekton.py` | Tekton pipeline ref and task name strings for Windows VM automation |
| `timeouts.py` | `TIMEOUT_*` integers and `TCP_TIMEOUT_30SEC` |
| `virt.py` | Virtctl commands, migration/eviction values, Windows version tags, CPU/memory topology, VM hardware constants |

Each submodule docstring lists what belongs there and what belongs elsewhere.

---

## Utility functions (`utilities/`)

Shared non-fixture logic lives under `utilities/`. Monolithic modules are being split into
thematic subpackages over time (same model as `utilities/constants/`).

### Placement

| Location | Use for |
| --- | --- |
| `utilities/cluster.py` | Cluster-wide operations (oc commands, node operations, cluster state) |
| `utilities/infra.py` | Infrastructure helpers (SSH, networking infrastructure, pod operations) |
| `utilities/virt.py` | VM lifecycle, VMI operations, migration helpers |
| `utilities/storage.py` | Storage operations (PVC, DataVolume, StorageClass) |
| Other `utilities/*.py` | Domain-specific helpers (HCO, monitoring, artifactory, …) |

When a module grows into a package (e.g. `utilities/virt/`), add functions to the submodule
that matches the concern and import from there:

```python
from utilities.virt.migration import migrate_vm_and_verify
```

Small single-purpose modules (`exceptions.py`, `logger.py`, …) may remain as single files
until splitting improves clarity.

**Never** add functions to the wrong domain module — match the table above.

---

## Fixtures (`tests/fixtures/` and `conftest.py`)

Pytest fixtures provide test setup and teardown. Fixture **definitions** for shared use are
moving into `tests/fixtures/`; `conftest.py` files register plugins and hold feature-local
fixtures only.

### Hierarchy

| File / directory | Role |
| --- | --- |
| [`conftest.py`](../conftest.py) | Pytest hooks, session configuration, `pytest_plugins` registration |
| [`tests/conftest.py`](../tests/conftest.py) | Cross-team fixtures still being consolidated |
| `tests/<team>/<feature>/conftest.py` | Feature-local fixtures when needed |
| `tests/fixtures/<team>/<topic>.py` | Shared fixture implementations |

### `tests/fixtures/` package

Shared fixtures are defined in Python modules under `tests/fixtures/`, grouped by team and topic:

```
tests/fixtures/
    network/
        l2_bridge.py
        cluster.py
```

Register new fixture modules in the root `conftest.py` `pytest_plugins` list:

```python
pytest_plugins = [
    "tests.fixtures.network.l2_bridge",
    "tests.fixtures.network.cluster",
]
```

Add a new entry when introducing a fixture module used across multiple test directories.

### Rules

- **`conftest.py` is for fixtures only** — no helper functions, utility functions, or classes.
- **Fixture names are nouns** — describe what the fixture provides (`vm_with_disk`), not an action
  (`create_vm_with_disk`).
- **One action per fixture** — split combined setup into separate fixtures composed by tests or
  `@pytest.mark.usefixtures`.
- **Return or yield the resource** — even setup-only fixtures should yield the created object.
- **Use `@pytest.mark.usefixtures`** when the test does not use the fixture return value.
- **Feature-local helpers** — place in `<feature_dir>/utils.py`, not in `conftest.py`.

Fixture scope, ordering, and logging rules are in [AGENTS.md](../AGENTS.md) and
[CODING_AND_STYLE_GUIDE.md](CODING_AND_STYLE_GUIDE.md).
