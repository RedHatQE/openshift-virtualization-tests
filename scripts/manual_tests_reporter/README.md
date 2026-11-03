<!-- Co-authored-by: Claude <noreply@anthropic.com> -->
# Manual Tests Reporter for Datadog Test Visibility

Interactive CLI that collects tests marked with `@pytest.mark.manual`,
shows full test context (docstrings, markers, preconditions) one-by-one,
lets the tester mark each as pass/fail/skip, and uploads the results to
**Datadog Test Optimization** as a JUnit XML report via `datadog-ci junit upload`.

## Usage

```bash
# Interactive run for a team directory (team derived from the folder)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/network --from-cluster

# With filters and explicit attributes
# Note: non-dry-run uploads require BUNDLE, OCP, CNV_XY_VER,
# CLUSTER_NAME, CLUSTER_DOMAIN, SC and CHANNEL — provide them via flags,
# a config file (~/.config/manual_tests_reporter/config.yaml or --config),
# or --from-cluster (see below).
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/storage -m "gating" -k test_snapshot \
    --bundle v4.22.0.rhel9-102 --tier TIER-2 --from-cluster

# Dry run (no upload)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/virt --dry-run --from-cluster

# Batch mode (non-interactive, e.g. retry after upload failure)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/network --batch-file manual_results_20260101_120000_123456.yaml --from-cluster
```

## Prerequisites

- `datadog-ci` must be installed and on `PATH`:

  ```bash
  npm install -g @datadog/datadog-ci
  ```

- `DATADOG_API_KEY` (or `DD_API_KEY`) environment variable must be set.
- `DATADOG_SITE` (or `DD_SITE`) for non-US1 sites (e.g. `datadoghq.eu`).
- Cluster access (a kubeconfig) is only needed for `--from-cluster`. Scan,
  batch, and dry-run runs work on hosts without a kubeconfig — cluster modules
  load lazily and their failure is reported cleanly when `--from-cluster` is
  used.
- A `KUBECONFIG` pointing at an unreachable or black-holed address (e.g. a
  stale kubeconfig for a decommissioned cluster) delays *every* invocation by
  the TCP connect timeout (minutes), even for cluster-independent runs — the
  utilities package resolves cluster architecture at import time. Fix or unset
  `KUBECONFIG` for cluster-less runs.

See `env.example` for the full list.

## Config file

Optional YAML defaults so repeated runs do not need the same CLI flags:

```yaml
# ~/.config/manual_tests_reporter/config.yaml (or pass --config <path>)
tests-dir: tests/network
tier: TIER-2
bundle: v4.22.0.rhel9-102
cnv-version: "4.22"
ocp-version: "4.19.0"
cluster-name: bm15a
cluster-domain: bm15a.example.com
sc: ocs-storagecluster-ceph-rbd
channel: stable
service: cnv-manual-tests
```

Every key is optional; unknown keys are rejected. The `arch` key was removed
(the arch tag is no longer uploaded) — delete it from an existing config
file; the loader rejects it with a hint. Retry files recorded before the
removal keep their saved `ARCH` attribute on replay. The file is picked up
automatically from `~/.config/manual_tests_reporter/config.yaml` when it
exists, or explicitly via `--config <path>`. A `tests-dir` starting with
`~` is expanded; like `--tests-dir`, relative paths resolve against the
directory the tool is launched from. Values must be non-empty strings —
quote values that look like numbers or booleans (e.g.
`cnv-version: '4.22'`, `tier: 'true'`); unquoted, YAML parses them as
numbers/booleans and the loader rejects them.

Precedence (highest first):

1. CLI flags
2. Batch-file metadata and saved attributes (a retry replays its recorded
   run — config defaults are ignored only for the attributes the retry
   file restores, with a note listing them, and still fill any gaps the
   saved attributes leave; the Datadog service and scan directory still
   come from the current CLI/config. A retry combined with `--from-cluster`
   is *not* a replay: cluster-derived values replace the saved attributes)
3. This config file
4. Cluster-derived values (`--from-cluster`)
5. TEAM derived from the tests directory — the only fresh-run source of
   TEAM, never applied to a replayed retry (see Team derivation)

Config values therefore behave like pre-set CLI flags: they override
cluster-derived attributes on fresh runs, while a one-off CLI flag still
wins for a single run. `--dry-run` shows the effective values.

## How it works

1. **Collect** — scans the tests directory for `@pytest.mark.manual` tests
   (module `pytestmark`, class, or test decorator level) and extracts
   docstrings, markers, fixtures, and Polarion IDs.
2. **Interactive verdicts** — each test is displayed with full context;
   the tester marks it pass / fail (with defect classification) / skip.
   Quit (`q`) or an interrupt (Ctrl-C / Ctrl-D) saves the results
   collected so far to a retry file and exits without uploading
   anything.
3. **Report** — a JUnit XML report is built: one `<testsuite>` per run,
   one `<testcase>` per manual test, with run attributes (team, bundle,
   cluster, …) and Polarion IDs as properties. Durations are not
   tracked for manual verdicts, so suites and testcases report `time="0"`.
4. **Upload** — `datadog-ci junit upload --service cnv-manual-tests`
   pushes the report so manual runs appear in Test Optimization next to
   CI runs. Every uploaded run carries the tag `manual:true` (in addition
   to run attributes), so manual results can be filtered apart from CI
   runs in Datadog Test Optimization.

Exit statuses: successful uploads and clean exits — including quitting with
`q` or an interrupt before any upload — exit 0; upload, report, or
configuration/validation errors (missing required attributes, missing API key
or `datadog-ci`, invalid batch file or marker expression) exit 1.

### Required run attributes

Runs that upload (i.e. without `--dry-run`) require the run attributes
`BUNDLE`, `OCP`, `CNV_XY_VER`, `CLUSTER_NAME`, `CLUSTER_DOMAIN`,
`SC` and `CHANNEL`. Provide them via the corresponding CLI flags, a config
file (see [Config file](#config-file)), or auto-fill them from the connected cluster with `--from-cluster`
(explicit CLI values override cluster-derived ones).

### Batch file format

Batch mode reads pre-filled verdicts from a YAML file (also written
automatically on upload failure or early quit for retry):

```yaml
metadata:
  bundle: v4.22.0        # optional, fills --bundle if not given
  attributes:            # optional, saved run attributes from a retry file;
    - key: TEAM          # each entry must be a {key: str, value: str} dict
      value: NETWORK
results:
  - test: "tests/foo/test_bar.py::TestClass::test_method"
    status: passed       # passed / failed / skipped (case-insensitive)
    comment: "optional"
    issue_type_label: "Product Bug"   # optional, failure classification
```

When `attributes` are restored (a retry replay), the saved values win over
`metadata.bundle`; the metadata value fills only keys the saved list lacks.
A `metadata.team` key is ignored — TEAM is derived from the tests directory
(see below) or restored with the saved run.

Notes:

- Each `test` value must be a node ID collectible from `--tests-dir`
  (respecting the `-m`/`-k` filters) to keep its Polarion linkage. Entries
  matching no collected test still upload, but lose Polarion linkage and
  produce a warning — check filters and test names when retrying.
- `attributes` entries are validated at load time: each must be a dict with
  string `key` and `value` fields.

On upload failure the results are saved to a timestamped YAML file —
retry with `--batch-file <file>`. The JUnit XML report is written to a
system temp directory: it is deleted after a successful upload and kept
(its path printed) only when the upload fails.

### Team derivation

There is no `--team` flag: TEAM is derived from the scanned tests directory —
the folder directly under `tests/` (or the selected folder itself), mapped to
the Datadog team:

| Folder | TEAM |
|---|---|
| network | NETWORK |
| storage | STORAGE |
| data_protection | STORAGE |
| virt | VIRT |
| observability | IUO |
| infrastructure | INFRASTRUCTURE |
| install_upgrade_operators | IUO |
| chaos | CHAOS |
| after_cluster_deploy_sanity | IUO |
| deprecated_api | IUO |
| post_test_alerts | IUO |
| scale | SCALE |

A directory that maps to no team (e.g. the whole `tests/` root) uploads
without a TEAM attribute. A retry replay keeps the TEAM recorded in its saved
attributes.

## Modules

| Module | Description |
|--------|-------------|
| `manual_tests_reporter.py` | CLI entry point (interactive + batch modes) |
| `collector.py` | `@pytest.mark.manual` test discovery with full context |
| `cluster_info.py` | Auto-fill run attributes from a connected cluster |
| `config.py` | Optional YAML config file with default run attributes |
| `junit_report.py` | JUnit XML builder + `datadog-ci` uploader |

## Running Tests

```bash
uv run pytest scripts/manual_tests_reporter/tests -c scripts/manual_tests_reporter/tests/pytest.ini
```

Or via the tox entry point, as CI runs it:

```bash
uv run tox -e scripts-unittests
```

## Origin

This tool replaces the ReportPortal manual reporter introduced in
https://github.com/RedHatQE/openshift-virtualization-tests/pull/5207.
