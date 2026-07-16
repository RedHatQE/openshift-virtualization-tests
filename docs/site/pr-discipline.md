# Pull Request Discipline

You want to contribute code and have your Pull Request (PR) merged as quickly as possible. Following these structural guidelines ensures your PR passes automated checks, remains focused on a single topic, and meets the review standards required for merging into the repository.

## Prerequisites

- Git installed and configured with your real name and email.
- The `uv` tool installed for managing dependencies and running test environments.

## Quick Example: The Ideal PR Workflow

The fastest path to getting code merged looks like this:

```bash
# 1. Branch for ONE specific feature or fix
git checkout -b fix-network-l2-bridge-timeout

# ... make your changes ...

# 2. Run all local checks before committing
uv run pre-commit run --all-files
uv run tox
uv run tox -e utilities-unittests

# 3. Commit with a descriptive title and DCO signature (-s)
git commit -s -m "fix(network): increase timeout for L2 bridge creation"

# 4. Push and create PR
git push -u origin fix-network-l2-bridge-timeout
```

## Step-by-Step Guide

### Step 1: Keep It Focused (Single-Topic Rule)

Every PR must address exactly ONE topic.

- **Do NOT** bundle unrelated changes together.
- **Do NOT** slip in "drive-by" refactoring unless it directly supports your fix.
- If you notice unrelated typos or bugs, create a separate branch and a separate PR.

### Step 2: Ensure the PR Title is Accurate

Your PR title must reflect the *actual change* being made, not merely a side effect.

| Incorrect Title | Correct Title | Why it's better |
|---|---|---|
| `skip artifactory` | `switch data source to DataSource API` | Describes *what* the code actually does |
| `fix failing test` | `fix(storage): update expected pvc size in test_disk.py` | Specific about the domain and fix |

### Step 3: Run Gating CI Checks Locally

Before you commit, you must verify your code passes all linting, formatting, and unit tests. Do not wait for the GitHub CI to tell you there are formatting errors.

```bash
# Run linters and formatters
uv run pre-commit run --all-files

# Run full CI collection and architecture checks
uv run tox

# Verify utility functions have required coverage
uv run tox -e utilities-unittests
```

> **Warning:** Fix all failures before committing. **Never** use `--no-verify` to bypass hooks.

### Step 4: Sign Your Commits (DCO)

All commits require a Developer Certificate of Origin (DCO) signature. This is enforced by CI.

Use the `-s` or `--signoff` flag when committing:
```bash
git commit -s -m "feat(virt): add STD for hotplug scenarios"
```

This automatically appends the required trailer to your commit message:
`Signed-off-by: Your Name <your.email@example.com>`

### Step 5: Fill Out the PR Template Completely

When you open a PR, a template is provided automatically. You **must** keep the mandatory headings and fill them out with meaningful content.

- `##### What this PR does / why we need it:` - Explain the *motivation* (the "why"). Do not leave this blank or use placeholders like `N/A`, `TBD`, or `-`.
- `##### Which issue(s) this PR fixes:` - List associated bugs or epics.
- `##### Special notes for reviewer:` - Highlight areas where you want specific feedback.
- `##### jira-ticket:` - Provide the full URL to the Jira ticket, or explicitly write `NONE`.

## Advanced Usage

### Using Draft PRs

Use Draft PRs to signal that work is intentionally incomplete.

- **When to use:** You have open design questions, failing CI that you are still debugging, or unresolved blockers.
- **When NOT to use:** The PR is ready for review.
- **Rule:** Never merge a PR (or ask for it to be merged) if it has known unresolved issues. Fix them, or document them in Jira and link them before marking the PR as Ready for Review.

### Fixing a Missing DCO Signature

If you forgot to sign a commit and the DCO check fails in GitHub, you can fix it locally:

**If it's just the last commit:**
```bash
git commit --amend -s --no-edit
git push --force-with-lease
```

**If you need to sign multiple older commits:**
```bash
git rebase --signoff origin/main
git push --force-with-lease
```

## Troubleshooting

### CI Fails with "Linter suppressions found"
The project strictly prohibits linter suppressions.
- **Problem:** You added `# noqa`, `# type: ignore`, or `# pylint: disable`.
- **Solution:** Remove the comment and **fix the code** so the linter is satisfied. If you believe the linter is genuinely wrong, you must get explicit approval during code review.

### Tests fail collection during `tox`
- **Problem:** Code fails in the `pytest-check-*` tox environments.
- **Solution:** This usually means a test file has a syntax error, a bad import, or a `__test__ = False` directive being misused. Ensure implemented tests do not have `__test__ = False` (this is only for placeholder STDs). Check your fixture definitions and imports. See [Code Organization](docs/CODE_ORGANIZATION.md) for import and fixture rules.

## Related Pages

- [Code Quality & Pre-commits](code-quality.html)
- [Test Design Workflow (STP/STD)](test-design-workflow.html)
- [Implementing New Tests](implementing-tests.html)
