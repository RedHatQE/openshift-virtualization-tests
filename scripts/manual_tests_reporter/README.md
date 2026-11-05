<!-- Co-authored-by: Claude <noreply@anthropic.com> -->
# Manual Tests Reporter — JUnit report for manual test runs

Interactive CLI that collects tests marked with `@pytest.mark.manual`,
shows full test context (docstrings, markers, preconditions) one-by-one,
lets the tester mark each as pass/fail/skip, and writes the results to a
**JUnit XML report**.

The tool does **not** push to Datadog. The report it writes carries every
run attribute and the failure classification as `dd_tags[...]`, so the same
file can be uploaded later — by Jenkins or by hand — and land on the same
Datadog tests and tags as a CI run.

## Usage

```bash
# Interactive run for a team directory (team derived from the folder)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/network --from-cluster

# With filters and explicit attributes
# Note: a complete report requires cnv_version, cnv_xy_version, ocp_version,
# cluster, cluster_domain, storage_class, cnv_channel and owner — provide them
# via flags, a config file (~/.config/manual_tests_reporter/config.yaml or
# --config), or --from-cluster (see below).
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/storage -m "gating" -k test_snapshot \
    --bundle v4.22.0.rhel9-102 --tier 2 --from-cluster

# Choose where the report is written (default: ./xunit_results.xml)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/virt --from-cluster --junit-output /tmp/manual_virt.xml

# Dry run (prints the resolved attributes; writes nothing)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/virt --dry-run --from-cluster

# Batch mode (non-interactive, e.g. retry after an interrupted run)
uv run python -m scripts.manual_tests_reporter.manual_tests_reporter \
    --tests-dir tests/network --batch-file manual_results_20260101_120000_123456.yaml --from-cluster
```

## Prerequisites

No Datadog credentials and no `datadog-ci` installation are needed to
produce a report. Uploading one later needs both, in the environment that
performs the upload:

```bash
npm install -g @datadog/datadog-ci
export DATADOG_API_KEY="<key>"
datadog-ci junit upload --service cnv-qe-tests xunit_results.xml
```

- Cluster access (a kubeconfig) is only needed for `--from-cluster`. Scan,
  batch, and dry-run runs work on hosts without a kubeconfig — cluster modules
  load lazily and their failure is reported cleanly when `--from-cluster` is
  used.
- A `KUBECONFIG` pointing at an unreachable or black-holed address (e.g. a
  stale kubeconfig for a decommissioned cluster) delays *every* invocation by
  the TCP connect timeout (minutes), even for cluster-independent runs — the
  utilities package resolves cluster architecture at import time. Fix or unset
  `KUBECONFIG` for cluster-less runs.

See `env.example` for the variables this tool honours (`KUBECONFIG` for `--from-cluster`, the architecture override for the utilities import chain) and for the separate upload step.

## Config file

Optional YAML defaults so repeated runs do not need the same CLI flags:

```yaml
# ~/.config/manual_tests_reporter/config.yaml (or pass --config <path>)
tests-dir: tests/network
tier: '2'
bundle: v4.22.0.rhel9-102
cnv-version: "4.22"
owner: tester@redhat.com
ocp-version: "4.19.0"
cluster-name: bm15a
cluster-domain: bm15a.example.com
cluster-id: bm15a-tjxpz
sc: ocs-storagecluster-ceph-rbd
channel: stable
ip-stack: ipv4
hco-bundle-version: v4.22.0.rhel9-102
```

Every key is optional; unknown keys are rejected. The complete accepted set,
with the run attribute each one sets:

| Config key | Run attribute |
|---|---|
| `tests-dir` | *(not an attribute — the scanned directory)* |
| `bundle` | *(not an attribute — derives `cnv_version` + `cnv_xy_version`)* |
| `tier` | `tier` (bare number) |
| `cnv-version` | `cnv_xy_version` |
| `ocp-version` | `ocp_version` |
| `cluster-name` | `cluster` |
| `cluster-domain` | `cluster_domain` |
| `cluster-id` | `cluster_id` |
| `sc` | `storage_class` |
| `channel` | `cnv_channel` |
| `owner` | `owner` |
| `ip-stack` | `ip_stack` |
| `iib-image` | `iib_image` |
| `hco-bundle-version` | `hco_bundle_version` |
| `rootcoz-url` | `rootcoz.url` | The file is picked up
automatically from `~/.config/manual_tests_reporter/config.yaml` when it
exists, or explicitly via `--config <path>`. A `tests-dir` starting with
`~` is expanded; like `--tests-dir`, relative paths resolve against the
directory the tool is launched from. Values must be non-empty strings —
quote values that look like numbers or booleans (e.g.
`cnv-version: '4.22'`, `tier: '2'`); unquoted, YAML parses them as
numbers/booleans and the loader rejects them.

The `service` key was removed: the reporter no longer tags a Datadog
service itself — pass `--service` to `datadog-ci` at upload time (the
Jenkins pipeline uses `cnv-qe-tests`). The `team` and `arch`
keys were removed: TEAM is now derived from the
tests directory and no arch tag is emitted — delete either
key from an existing config file (the loader rejects them with a hint).
Legacy retry files keep their recorded `arch` tag on replay (a replay
reproduces the recorded run); only new runs drop it.

Precedence (highest first):

1. CLI flags
2. Batch-file metadata and saved attributes (a retry replays its recorded
   run — config defaults are ignored only for the attributes the retry
   file restores, with a note listing them, and still fill any gaps the
   saved attributes leave; the scan directory and output path still come
   from the current CLI/config. A retry combined with `--from-cluster`
   is *not* a replay: cluster-derived values replace the saved attributes)
3. This config file
4. Cluster-derived values (`--from-cluster`)
5. team derived from the tests directory — the only fresh-run source of
   the team, never applied to a replayed retry (see Team derivation).
   `owner` is the one exception to replay precedence: it always reflects
   the user pushing *this* run (CLI/config override, else the git
   `user.email` of the tests checkout), so a saved `owner` is dropped on
   a retry.

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
   collected so far to a retry file and exits without writing a
   report.
3. **Report** — a JUnit XML report is written (default
   `./xunit_results.xml`, override with `--junit-output`): one
   `<testsuite>` per run, one `<testcase>` per manual test. Run attributes,
   the Polarion ID, and the failure classification are emitted as
   `dd_tags[...]` properties. Durations are not tracked for manual
   verdicts, so suites and testcases report `time="0"`.
4. **Upload (out of scope)** — the report is the deliverable. Uploading it
   later with `datadog-ci junit upload` reproduces the tag set below.
   Every run carries `manual:true`, so manual results can be filtered apart
   from CI runs.

### Tag set (Jenkins parity)

The report carries the same tags the Jenkins `datadog-upload-results`
pipeline attaches, all as `dd_tags[...]` properties on every testcase, so
both run types land on the same Datadog tests with the same facets:

| Tag | Source for a manual run |
|---|---|
| `job_name` | synthetic: `manual-tests-<team>` (`manual-tests` with no team) |
| `build_number` | synthetic: epoch seconds of the run |
| `team` | derived from the scanned tests directory |
| `tier` | `--tier`, normalized to the bare number |
| `cnv_version`, `cnv_xy_version` | `--bundle` / `--cnv-version` / cluster |
| `ocp_version` | `--ocp-version` / cluster |
| `cluster`, `cluster_domain`, `cluster_id` | `--cluster-name` / `--cluster-domain` / `--cluster-id` / cluster |
| `storage_class` | `--sc` / cluster |
| `cnv_channel` | `--channel` / cluster |
| `cni` | cluster (`Network/cluster` `status.networkType`) |
| `owner` | `--owner`, else git `user.email` of the tests checkout |
| `marker` | `-m` expression of the run |
| `test_case_name` | `manual.<scanned-folder-name>` |
| `hco_bundle_version`, `iib_image`, `ip_stack`, `rootcoz.url` | the matching CLI flags / config keys |
| `manual` | always `true` |
| `tfa.classification` | failures only — see below |

Failure classification: each failed testcase carries
`dd_tags[tfa.classification]` using the RootCoz/Datadog vocabulary
(`product_bug`, `code_issue`, `infrastructure`, `unknown`), mapped from the
defect label the tester picks:

| Defect choice | `tfa.classification` |
|---|---|
| Product Bug | `product_bug` |
| Automation Bug | `code_issue` |
| System Issue | `infrastructure` |
| To Investigate | `unknown` |
| No Defect | `unknown` |

RootCoz's vocabulary has exactly four values (`CODE ISSUE`, `PRODUCT BUG`,
`INFRASTRUCTURE`, `UNKNOWN`), so **"To Investigate", "No Defect" and an
unclassified failure all fold into `unknown`**. That conflation is
deliberate and accepted: it keeps the facet enumerable, and the tester's
exact choice remains queryable on the `<failure type="…">` element (and in
the retry YAML), which is where "confirmed not a defect" is distinguished
from "nobody looked yet".

The defect label is also kept on the `<failure type="...">` element.

Also mirrored from Jenkins so the same node ID resolves to the same Datadog
test instead of a parallel "Manual" universe:

- suite name (`pytest`) and the artifact file name (`xunit_results.xml`);
- `test_case_name` uses the `manual.<scanned-folder-name>` form (the
  basename of `--tests-dir`, e.g. `manual.network`).

Deliberately not emitted, with the reason:

| Omitted tag | Why |
|---|---|
| `build_url` | a manual run has no Jenkins build to link |
| `gating` | a CI-only marker; `manual:true` is the manual counterpart |
| `<label>:true` and `label` | JOB_METADATA labels — a manual run has no job definition to read them from |
| `job_display_name` | JOB_METADATA display name; the synthetic `job_name` already identifies the run |
| `multi_nics` | JOB_METADATA requirement (does the *job* need multiple NICs). The cluster's multus NAD count is not the same fact, so it is not guessed |
| `arch` | the production Jenkins path (`buildTagsForDownstream`, the `datadog-upload-results` job) does not emit it either — only the legacy sidecar `buildTagsArg` did |

Tag values are sanitized to Datadog's character set before they are written,
and Datadog applies the same normalization server-side to whatever an uploader
sends: per the tagging docs, "all other characters (including commas, emoji,
backslashes, and spaces) are converted to underscores". Jenkins therefore
stores `marker:smoke_and_not_tier3` for an unescaped `smoke and not tier3`
just as this report does for its pre-sanitized value — multi-word markers
converge on the same facet value rather than diverging. The same rule is why
the team strings above (`CNV Network`, `CNV Install, Upgrade and Operators`)
land on `CNV_Network` / `CNV_Install__Upgrade_and_Operators` for CI and for a
manual run alike.

With `--from-cluster`, `cluster_id` is the common prefix of the cluster's
node names (nodes are `<cluster_id>-master-0`, `<cluster_id>-worker-N`) —
the provisioned cluster name, matching how the Jenkins pipeline derives its
`CLUSTER_ID`; the `cluster` tag carries the Infrastructure CR's shorter
`infrastructureName`.

`classname` and `name` reproduce pytest's own `--junitxml` mangling
(`tests.network.test_demo.TestDemo` + `test_param[1]`), so a manual result
resolves to the same Datadog test as the CI run instead of a parallel "Manual"
universe.

One known gap: the collector reads source with `ast` and cannot know a test's
parametrization, so a manual verdict on a **parametrized** test is reported as
`test_x` while `pytest --junitxml` reports `test_x[1]`, `test_x[2]`, … and the
two do not merge. The collector logs a warning when a collected manual test
carries `parametrize`; no manual-marked test in this repo is parametrized today.

Exit statuses: a written report and clean exits — including quitting with
`q` or an interrupt before writing — exit 0; report or
configuration/validation errors (missing required attributes, invalid batch
file or marker expression, unwritable output path) exit 1.

### Required run attributes

Runs that write a report (i.e. without `--dry-run`) require the run attributes
`cnv_version`, `cnv_xy_version`, `ocp_version`, `cluster`, `cluster_domain`,
`storage_class`, `cnv_channel` and `owner`. Provide them via the corresponding
CLI flags (`--bundle` derives both CNV versions; `owner` defaults to the git
`user.email` of the tests checkout), a config file (see
[Config file](#config-file)), or auto-fill them from the connected cluster
with `--from-cluster` (explicit CLI values override cluster-derived ones).

### Batch file format

Batch mode reads pre-filled verdicts from a YAML file (also written
automatically on report-write failure or early quit for retry):

```yaml
metadata:
  bundle: v4.22.0        # optional, fills --bundle on a fresh run
  attributes:            # optional, saved run attributes from a retry file;
    - key: team          # each entry must be a {key: str, value: str} dict
      value: NETWORK
results:
  - test: "tests/foo/test_bar.py::TestClass::test_method"
    status: passed       # passed / failed / skipped (case-insensitive)
    comment: "optional"
    issue_type_label: "Product Bug"   # optional, failure classification
```

When `attributes` are restored (a retry replay), the recorded run is
reproduced exactly: the saved values stand and the metadata bundle is not
re-applied (`metadata.bundle` feeds CNV-version derivation on fresh runs
over results-only batch files, and gap-fills any CNV version a partial
saved list lacks; recorded values are never overridden). A
`metadata.team` key is ignored — the team is derived from the tests
directory (see below) or restored with the saved run. Retry files saved
before the Jenkins-parity rename migrate on load: upper-case keys map to
their modern names (`TEAM`→`team`, `OCP`→`ocp_version`, …) and a `BUNDLE`
entry converts to its derived `cnv_version`/`cnv_xy_version`, so legacy
retries replay cleanly; keys without a modern equivalent and unknown keys
stay verbatim. A legacy `TIER` value is normalized too (`TIER-2`→`2`).

Notes:

- Each `test` value must be a node ID collectible from `--tests-dir`
  (respecting the `-m`/`-k` filters) to keep its Polarion linkage. Entries
  matching no collected test still appear, but lose Polarion linkage and
  produce a warning — check filters and test names when retrying.
- `attributes` entries are validated at load time: each must be a dict with
  string `key` and `value` fields.

On a report-write failure (or an interrupt during it) the results are
saved to a timestamped YAML file — retry with `--batch-file <file>`. The
JUnit XML report is written to `--junit-output` (default
`./xunit_results.xml`) and is always kept; that file is the deliverable.

### Team derivation

There is no `--team` flag: the team is derived from the scanned tests
directory — the folder directly under `tests/` (or the selected folder
itself), mapped to the Datadog team:

The values are the Jenkins `JOB_METADATA` team strings verbatim, because the
CI tag is `team:${metadata.team}` unchanged — a short label such as `NETWORK`
would put manual runs in a facet value no CI run ever writes.

Both sides feed the same server, and Datadog normalizes tag values there (the
tagging docs list the characters it keeps; "all other characters … are
converted to underscores"), so a CI `team:CNV Network` and this report's
`dd_tags[team]=CNV Network` reach the same facet value regardless of how the
underscores and letter case are finally rendered. The table's middle column is
the value written to the file; the right-hand column is what this tool's own
sanitizer produces, so it is **not** independent evidence of the live facet —
if you need the exact stored string (e.g. for an IUO filter), read it once off
the Datadog facet for an `install_upgrade_operators` CI run.

| Folder | value written | `dd_tags[team]` after local sanitizing |
|---|---|---|
| network | `CNV Network` | `CNV_Network` |
| storage | `Storage Platform` | `Storage_Platform` |
| data_protection | `Storage Platform` | `Storage_Platform` |
| virt | `CNV Virtualization` | `CNV_Virtualization` |
| observability | `CNV Install, Upgrade and Operators` | `CNV_Install__Upgrade_and_Operators` |
| infrastructure | `CNV Infrastructure` | `CNV_Infrastructure` |
| install_upgrade_operators | `CNV Install, Upgrade and Operators` | `CNV_Install__Upgrade_and_Operators` |
| after_cluster_deploy_sanity | `CNV Install, Upgrade and Operators` | `CNV_Install__Upgrade_and_Operators` |
| deprecated_api | `CNV Install, Upgrade and Operators` | `CNV_Install__Upgrade_and_Operators` |
| post_test_alerts | `CNV Install, Upgrade and Operators` | `CNV_Install__Upgrade_and_Operators` |
| chaos | `CHAOS` | `CHAOS` |
| scale | `SCALE` | `SCALE` |

`chaos` and `scale` have no Jenkins job at all (no `tests/chaos` or `tests/scale`
suite exists in the CI job metadata), so there is no CI facet value to align
with; they keep their own values and remain manual-only facets.

A directory that maps to no team (e.g. the whole `tests/` root) produces a
report without a team attribute. A retry replay keeps the team recorded in its
saved attributes.

## Modules

| Module | Description |
|--------|-------------|
| `manual_tests_reporter.py` | CLI entry point (interactive + batch modes) |
| `collector.py` | `@pytest.mark.manual` test discovery with full context |
| `cluster_info.py` | Auto-fill run attributes from a connected cluster |
| `config.py` | Optional YAML config file with default run attributes |
| `versions.py` | CNV version-string parsing shared by the CLI and cluster collection |
| `junit_report.py` | JUnit XML builder (`dd_tags[...]` properties + failure classification) |

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
