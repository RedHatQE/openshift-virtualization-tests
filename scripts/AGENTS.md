# Scripts — AI Review and Development Standards

Supplemental guidance for the `scripts/` directory.
See the root [`AGENTS.md`](../AGENTS.md) for project-wide rules.

## Known Script Behaviors (do not "fix" these)

- **`scripts/coderabbit_retry/`** — idempotent; runs every 20 min with a 15-min timeout and processes only PRs owned by its bot account.
- **`scripts/reportportal/rp_utils/rp_client.py`** — uses contains-match semantics (`filter.cnt.attributeValue`) for bundle filtering; retry-upload intentionally lacks `polarion-testcase-id` preservation.
- **`scripts/tests_analyzer/pytest_marker_analyzer.py`** — `conftest_resolved=True` intentionally stops scanning further dependency paths to minimize regressions.
