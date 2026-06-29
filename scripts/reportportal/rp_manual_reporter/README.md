<!-- Co-authored-by: Claude <noreply@anthropic.com> -->
# Manual Test Reporter for ReportPortal

Push manual test results for unautomated STD (Standard Test Design) placeholder tests
to ReportPortal. These are tests marked with `__test__ = False` that are not yet automated.

---

## Table of Contents

- [Authentication](#authentication)
- [Launch Attributes](#launch-attributes)
- [Usage Examples](#usage-examples)
- [Interactive Mode](#interactive-mode)
- [Batch YAML Format](#batch-yaml-format)
- [Failure Recovery](#failure-recovery)
- [CLI Reference](#cli-reference)

---

## Authentication

The reporter authenticates with ReportPortal using an API token.

1. Log in to your ReportPortal instance.
2. Click your avatar (top-right) → **API Keys**.
3. Generate a new key or copy an existing one.
4. Export the connection settings as environment variables:

```bash
export REPORT_PORTAL_URL="https://your-reportportal-instance.example.com"
export REPORT_PORTAL_PROJECT="your-project"
export REPORT_PORTAL_TOKEN="your-api-key-here"
```

> **Tip:** Add the exports to your shell profile (`~/.bashrc`, `~/.zshrc`) so you
> don't have to set them every session.

---

## Launch Attributes

Every ReportPortal launch is tagged with attributes that describe the environment
under test. Attributes can be auto-filled from a connected cluster, provided by the
user, or set automatically.

### Auto-filled from cluster (`--from-cluster`)

When `--from-cluster` is passed, the tool queries the connected OpenShift cluster
and populates these attributes automatically:

| Attribute        | Description                                    | Example                          |
|------------------|------------------------------------------------|----------------------------------|
| `ARCH`           | CPU architecture of the cluster nodes          | `amd64`                          |
| `OCP`            | OpenShift platform version                     | `4.22.0-ec.4`                    |
| `CNV_XY_VER`     | CNV major.minor version                        | `4.22`                           |
| `BUNDLE`         | Full CNV/HCO bundle version                    | `v4.22.0.rhel9-102`              |
| `CLUSTER_NAME`   | Cluster infrastructure name                    | `bm15a-tlv2`                     |
| `CLUSTER_DOMAIN` | Cluster base domain                            | `bm15a-tlv2.abi.cnv-qe.rhood.us`|
| `SC`             | Default storage class                          | `OCS`                            |
| `CHANNEL`        | HCO subscription channel                       | `candidate`                      |

### User-provided (optional)

| Attribute | Description                          | Examples                            |
|-----------|--------------------------------------|-------------------------------------|
| `TEAM`    | QE team that owns the test results. Auto-inferred from `--tests-dir` if not set. | `NETWORK`, `STORAGE`, `VIRT`, `IUO` |

### User-provided tier (optional)

| Attribute | Description                          | Examples             |
|-----------|--------------------------------------|----------------------|
| `TIER`    | Test tier level                      | `TIER-2`, `TIER-3`   |

### Bundle-to-version derivation

When `--bundle` is provided explicitly, `CNV_XY_VER` is automatically derived
from the bundle version (e.g., `v4.22.0.rhel9-102` → `4.22`). This override
takes precedence over any cluster-detected `CNV_XY_VER`.

### Automatically set

| Attribute    | Description                                        |
|--------------|----------------------------------------------------|
| `MANUAL=true`| Distinguishes manual runs from automated CI runs   |

### Manual override (no cluster access)

If you don't have access to the cluster, provide all required attributes as CLI flags:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --bundle v4.22.0-test \
    --ocp-version 4.19.0 \
    --cnv-version 4.22 \
    --arch amd64 \
    --cluster-name my-cluster \
    --cluster-domain apps.my-cluster.example.com \
    --sc ocs-storagecluster-ceph-rbd \
    --channel stable \
    --tests-dir tests/network/
```

> **Note:** All 8 attributes above are mandatory. The tool will refuse to push
> if any are missing (unless running with `--dry-run`).

---

## Usage Examples

### Interactive mode (with cluster)

Auto-fill environment attributes from the connected cluster. Team is
auto-inferred from `--tests-dir`:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --from-cluster \
    --bundle v4.22.0-test \
    --tests-dir tests/network/
```

### Interactive mode (manual attributes)

Provide environment attributes manually when no cluster is connected:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --bundle v4.22.0-test \
    --ocp-version 4.19.0 \
    --cnv-version 4.22 \
    --arch amd64 \
    --cluster-name my-cluster \
    --cluster-domain apps.my-cluster.example.com \
    --sc ocs-storagecluster-ceph-rbd \
    --channel stable \
    --tests-dir tests/network/
```

### Batch mode (from YAML)

Submit pre-recorded results from a YAML file instead of going through
the interactive prompt:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --team NETWORK --bundle v4.22.0 --batch-file results.yaml
```

### Filter by directory

Scan only a specific team's tests (team is auto-inferred from path):

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --tests-dir tests/network/ --bundle v4.22.0
```

### Filter by marker

Collect only gating-marked placeholder tests:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --bundle v4.22.0 -m gating
```

### Filter by keyword

Collect only tests matching a keyword in the node ID:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --bundle v4.22.0 -k test_connectivity
```

### Dry run

Preview what would be reported without pushing anything to ReportPortal:

```bash
uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
    --bundle v4.22.0 --dry-run
```

---

## Interactive Mode

When no `--batch-file` is provided, the tool enters interactive mode:

1. **Test discovery** — Scans the repo for STD placeholder tests (`__test__ = False`),
   optionally filtered by `--tests-dir`, `-m` (marker), or `-k` (keyword).

2. **One-by-one review** — Each test is displayed with full context:
   - Module and class docstrings (STP links, preconditions)
   - Test docstring (steps, expected results)
   - Pytest markers and fixtures
   - Polarion test case ID

3. **Verdict prompt** — For each test, enter one of:

   | Key | Action                                                       |
   |-----|--------------------------------------------------------------|
   | `p` | **Pass** — mark the test as passed (pushed to RP)            |
   | `f` | **Fail** — mark the test as failed (pushed to RP)            |
   | `s` | **Skip** — move to the next test without recording anything  |
   | `q` | **Quit** — stop and push results collected so far            |

4. **Defect classification** — When you mark a test as **failed**, the tool prompts
   for a defect type:

   | Code | Defect Type |
   |------|-------------|
   | `1` | Product Bug — confirmed defect in the product |
   | `2` | Automation Bug — test code issue |
   | `3` | System Issue — environment or infrastructure problem |
   | `4` | To Investigate — failure not yet analyzed |
   | `5` | No Defect — false alarm or expected behavior |

   Invalid input is re-prompted until a valid code (1–5) is entered.
   The defect type is attached to the RP test item as an issue.

5. **Failure comment** — After selecting the defect type, the tool prompts for
   an optional comment (e.g., a bug ID like `MOCK-12345` or a brief description).

---

## Batch YAML Format

The batch file lists test results as a YAML document. Each entry specifies the
full pytest node ID, a status, and an optional comment:

```yaml
results:
  - test: "tests/storage/cbt/test_cbt.py::TestFullBackupRestore::test_full_backup_push_mode_restore"
    status: passed
    comment: "Verified manually on cluster xyz"
  - test: "tests/network/upgrade/test_upgrade_network.py::TestUpgradeNetwork::test_udn_vm_state"
    status: failed
    comment: "Bug MOCK-12345"
```

**Fields:**

| Field     | Required | Values                      | Description                        |
|-----------|----------|-----------------------------|------------------------------------|
| `test`    | Yes      | Full pytest node ID         | Identifies the placeholder test    |
| `status`  | Yes      | `passed`, `failed`, `skipped` | Test verdict                     |
| `comment` | No       | Free text                   | Bug ID, notes, or justification    |

---

## Failure Recovery

If the push to ReportPortal fails (network error, token expiry, server outage):

1. **Auto-save** — All collected results are automatically saved to a timestamped
   file:
   ```
   manual_results_<timestamp>.yaml
   ```
   This file uses the same format as the [batch YAML](#batch-yaml-format).

2. **Retry** — Once the issue is resolved, replay the saved results:
   ```bash
   uv run python -m scripts.reportportal.rp_manual_reporter.rp_manual_reporter \
       --team STORAGE --bundle v4.22.0 --batch-file manual_results_20250612_143022.yaml
   ```

No manual work is lost — you never have to re-enter verdicts.

### Recovery / Retry File

Recovery files (and manually-crafted retry files) may include an optional
`metadata` block alongside `results`. The reporter uses these fields to
restore context that was active when the results were originally collected:

```yaml
metadata:
  team: STORAGE
  bundle: v4.22.0.rhel9-102
  attributes:
    - { key: "BUNDLE", value: "v4.22.0.rhel9-102" }
    - { key: "CNV_XY_VER", value: "4.22" }
  saved_at: "2025-06-12T14:30:22"

results:
  - test: "tests/storage/cbt/test_cbt.py::TestFullBackupRestore::test_full_backup_push_mode_restore"
    status: passed
```

| Field                  | Description                                                       |
|------------------------|-------------------------------------------------------------------|
| `metadata.team`        | QE team name — used when `--team` is not passed on the CLI.       |
| `metadata.bundle`      | Bundle version — used when `--bundle` is not passed on the CLI.   |
| `metadata.attributes`  | Saved launch attributes applied as defaults for the retry launch. |
| `metadata.saved_at`    | ISO-8601 timestamp recording when the file was auto-saved.        |

---

## CLI Reference

| Option              | Required | Default         | Description                                          |
|---------------------|----------|-----------------|------------------------------------------------------|
| `--team`            | No       | Auto-inferred   | QE team name (`NETWORK`, `STORAGE`, `VIRT`, `IUO`). Auto-inferred from `--tests-dir` if not set. |
| `--from-cluster`    | No       | `false`         | Auto-fill launch attributes from the connected cluster |
| `--bundle`          | No*      | —               | CNV/HCO bundle version (e.g., `v4.22.0.rhel9-102`)   |
| `--cnv-version`     | No*      | —               | CNV major.minor version (e.g., `4.22`)                |
| `--arch`            | No*      | —               | Cluster CPU architecture (e.g., `amd64`)              |
| `--ocp-version`     | No*      | —               | OpenShift version (e.g., `4.22.0-ec.4`)               |
| `--cluster-name`    | No*      | —               | Cluster infrastructure name (e.g., `bm15a-tlv2`)     |
| `--cluster-domain`  | No*      | —               | Cluster base domain (e.g., `abi.cnv-qe.rhood.us`)    |
| `--sc`              | No*      | —               | Default storage class label (e.g., `OCS`)             |
| `--channel`         | No*      | —               | HCO subscription channel (e.g., `candidate`)          |
| `--tier`            | No       | —               | Test tier level (e.g., `TIER-2`, `TIER-3`)            |
| `--batch-file`      | No       | —               | Path to YAML file with pre-recorded results           |
| `--tests-dir`       | No       | `tests`         | Directory to scan for placeholder tests               |
| `-m` / `--marker`   | No       | —               | Filter tests by pytest marker expression              |
| `-k` / `--keyword`  | No       | —               | Filter tests by keyword in node ID                    |
| `--rp-url`          | No       | env `REPORT_PORTAL_URL`    | ReportPortal base URL              |
| `--rp-project`      | No       | env `REPORT_PORTAL_PROJECT` | ReportPortal project name         |
| `--rp-token`        | No       | env `REPORT_PORTAL_TOKEN`  | ReportPortal API token             |
| `--dry-run`         | No       | `false`         | Preview results without pushing to ReportPortal       |

> **\*** These flags are required when `--from-cluster` is not used. With
> `--from-cluster`, they are auto-filled but can still be passed to override
> specific values.
