# Polarion → Jira backfill

`polarion_jira_backfill.py` backfills Jira requirement links into test
function docstrings of this repository, as part of the code-first test
management migration (traceability lives in the code; Polarion is being
retired).

## Flow

`@pytest.mark.polarion("CNV-XXXXX")` marker → Polarion API (test case →
linked requirement) → Jira ID from the requirement's hyperlinks
(`/browse/CNV-XXXX` on issues.redhat.com / redhat.atlassian.net, or the
`jiraurl` custom field) → inserted into the test function's docstring.

Per test function:

- `Jira: https://redhat.atlassian.net/browse/<ID> # <skip-jira-utils-check>`
  lines are added (after any existing `Jira:` lines, otherwise at the top).
- The Polarion test-case ID moves from the `@pytest.mark.polarion("CNV-XXXX")`
  decorator into the docstring as a `Polarion: CNV-XXXX` line; the decorator
  is removed. Polarion marks inside `pytest.mark.parametrize` argvalues are
  stripped the same way (other marks are kept).
- Tests without a docstring get one: leading `#` comments above the test body
  become docstring text; single-line docstrings are expanded to multi-line.
- The edit is idempotent — re-running on an already-backfilled file changes
  nothing.

Files whose module docstring already has an STP link are skipped
(Test → STP → Jira is already complete); disable with `--no-skip-stp`.

## Usage

```bash
# Dry run (default) — show what would change
uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py \
  --tests-repo ~/git/openshift-virtualization-tests --dry-run

# Apply changes to the working tree
uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py \
  --tests-repo ~/git/openshift-virtualization-tests --apply

# Only build/refresh the Polarion ID -> Jira mapping cache (no file edits)
uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py \
  --tests-repo ~/git/openshift-virtualization-tests --mapping-only

# Single team / limit for testing
uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py \
  --tests-repo ~/git/openshift-virtualization-tests --team network --limit 5

# Open PRs (grouped by team, split into chunks of at most N files per PR)
uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py \
  --tests-repo ~/git/openshift-virtualization-tests --open-pr --max-files-per-pr 10
```

## PR mode

`--open-pr` applies the changes as PRs instead of editing the working tree:

- **The tool does not run on local code by default.** It clones `upstream/main`
  fresh from GitHub into a temporary directory under `/tmp` (override with
  `--clone-dir`; kept after the run with `--keep-clone` or when `--clone-dir`
  is given). The local checkout passed via `--tests-repo` is used only to
  discover the upstream and fork remote URLs. `--use-local-repo` opts out of
  cloning (not recommended).
- Changed files are grouped **by team** (first directory under `tests/`), then
  split into chunks of at most `--max-files-per-pr` files (default 10).
- `--max-prs N` opens at most N PRs (e.g. `--max-prs 1` for a test run);
  remaining files are skipped and picked up by a later run. No limit when
  not passed.
- Each group gets a branch `backfill/jira-links-<team>` (plus `-partN` when a
  team is split), branched from the upstream default branch (`--pr-base` to
  override), committed, pushed to your fork (`--pr-remote` to override;
  default: remote `fork`, else first non-origin remote), and opened as a PR
  against the upstream repo via `gh`.
- PR bodies follow the repository's pull request template.
- **pre-commit must pass** before any commit: if the repo has a
  `.pre-commit-config.yaml`, the tool runs `pre-commit run --files <changed>`
  on the changed files (falling back to `uvx pre-commit` if `pre-commit` is
  not on PATH). Auto-fixing hooks get one retry after re-staging; a second
  failure aborts that PR — hooks are never bypassed.
- Combine with `--dry-run` to only print the PR plan (the clone still
  happens, so the plan reflects upstream state).

## Mapping cache

- The Polarion test-case ID → requirement → Jira mapping is cached to
  `polarion-jira-mapping.json` (`--mapping-file`); re-runs use the cache and
  never re-query resolved IDs — **build the cache early, the Polarion API
  will not be around forever.**
- During resolution a progress line is logged periodically
  (`--progress-every N`; `1` = every ID, `0` = disable) with position,
  percentage, ok/flagged counts, elapsed time, and ETA.
- IDs whose test case is missing, has no linked requirement, or whose
  requirement has no Jira link are reported for manual review.

## Requirements

- A pylero config (`~/.pylero` or `./.pylero`) with credentials for
  `https://polarion.engineering.redhat.com/polarion`. For the Red Hat
  internal CA, set `cert_path` in the config or the `SSL_CERT_FILE` env var.
- `gh` (GitHub CLI), authenticated, for `--open-pr`.
