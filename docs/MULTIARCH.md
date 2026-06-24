# Multi-Architecture (Heterogeneous) Clusters

A heterogeneous cluster has worker nodes of more than one CPU architecture — for example, amd64 and arm64 workers coexisting on the same cluster. The test framework detects this automatically.

**Supported architectures:** `amd64`, `arm64`

## Overview

The `--cpu-arch` option selects which architecture(s) to target. Behavior depends on cluster type and the value passed:

| Test suite | Cluster | `--cpu-arch` | What runs |
| ---------- | ------- | ------------ | --------- |
| **Standard** | Homogeneous (single arch) | Omit — auto-detected from node labels | Standard regression tests |
| **Multiarch regression** | Heterogeneous (multiarch) | Single value — e.g. `amd64` or `arm64` | Full suite, scoped to nodes of that arch |
| **Multiarch-dedicated** | Heterogeneous (multiarch) | Comma-separated — e.g. `amd64,arm64` | Only tests marked with `multiarch` |

**On a heterogeneous cluster:**

- `--cpu-arch` is **required**. Omitting it raises `UnsupportedCPUArchitectureError`.
- Pass `--tc-file=tests/global_config.py` for regression runs (preferred — it auto-imports the multiarch config). `tests/global_config_multiarch.py` also works.
- For multiarch-dedicated tests, `--tc-file=tests/global_config_multiarch.py` is **required**.

**On a homogeneous cluster:**

- Run tests normally and do **not** pass `--cpu-arch`. Passing it raises `UnsupportedCPUArchitectureError`.

## Multiarch regression

Run the existing test suite against one architecture's nodes at a time.

```bash
# amd64 regression
uv run pytest --tc-file=tests/global_config.py --cpu-arch=amd64 ...

# arm64 regression
uv run pytest --tc-file=tests/global_config.py --cpu-arch=arm64 ...
```

## Multiarch-dedicated tests

Run tests that exercise behavior requiring multiple architectures simultaneously (e.g., golden image import across both archs, cross-arch scheduling).

```bash
uv run pytest --tc-file=tests/global_config_multiarch.py --cpu-arch=amd64,arm64 \
  -m "iuo and multiarch" ...
```

### Run requirements

- The cluster must be heterogeneous.
- `--cpu-arch` must list multiple architectures (e.g. `amd64,arm64`)
- Every collected test must have the `multiarch` marker — use `-m multiarch`, or point pytest at a path that contains only multiarch tests (e.g. a `multiarch/` subdirectory). If any non-multiarch test is collected, pytest raises `UnsupportedCPUArchitectureError`.

### Writing dedicated tests

Multiarch-dedicated tests must be fully isolated from regular tests. Do **not** reuse or modify existing fixtures and functions — create new ones dedicated to multiarch tests.

Mark the entire file or specific classes with the `multiarch` marker:

```python
# Module-level (preferred — marks the whole file)
pytestmark = [pytest.mark.multiarch]

# Class-level
@pytest.mark.multiarch
class TestMultiarchFeature:
    ...
```

The `multiarch` marker is **required** on any test that runs in multiarch-dedicated mode. It also prevents the test from being collected on homogeneous clusters.

Place multiarch tests in a `multiarch/` subdirectory or use `_multiarch` in the filename (repo convention, not enforced by pytest):

```
tests/
  install_upgrade_operators/
    hco_enablement_golden_image_updates/
      multiarch/
        test_multiarch_golden_images_support.py
  network/
    connectivity/
      test_pod_network_multiarch.py
```

### Framework constraints

Multiarch-dedicated runs (`--cpu-arch=amd64,arm64`) do not set a single target architecture. Tests must not rely on the helpers that regression runs provide:

| Helper | Multiarch regression | Multiarch-dedicated |
| ------ | -------------------- | ------------------- |
| `py_config["cpu_arch"]` | Set to selected arch | **Not set** |
| OS matrix keys in `py_config` (e.g. `latest_rhel_os_dict`) | Generated for selected arch | **Not generated** |
| `schedulable_nodes` | Nodes of selected arch only | All schedulable nodes — filter by arch in the test |
