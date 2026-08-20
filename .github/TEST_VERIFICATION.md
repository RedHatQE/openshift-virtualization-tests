# Test verification (draft UX)

Authors prove what they ran **only in the PR description**. No slash commands and no verification comments.

## Flow

1. Add **`verified`** label or comment **`/test-plan`** → CodeRabbit posts a test plan.
2. Automation appends **Test verification** to the PR description and sets **`test-verification`** to *Action required*.
3. Author edits the PR description: checks each box and fills **ran** / **ci** / **skip** / **na** with evidence.
4. On save → **`test-verification`** turns green or red (errors in the Checks tab).
5. New code push removes the section and resets the check (clean rebase preserved).

## Dispositions

| Value | Meaning |
|-------|---------|
| **ran** | You executed this (command/cluster) |
| **ci** | Jenkins or GitHub Actions ran it (URL) |
| **skip** | You disagree with this plan item — explain why (min 30 chars) |
| **na** | Not applicable — explain why (min 30 chars) |

If a reviewer wants changes, the author **edits the PR description** again (e.g. change `skip` → `ran` with evidence) and saves.

## Example PR description

```markdown
<!-- test-verification-start -->
### Test verification (required for merge)
_Test plan: [view plan](...) · Tree: `a1b2c3d`_

- [x] **1.** `tests/network/sriov/test_memory_hotplug.py` — **ran:** uv run pytest ... on cluster dev-sriov-01
- [x] **2.** `Run smoke tests` — **skip:** Change limited to SR-IOV dir; smoke targets storage only per plan
<!-- test-verification-end -->
```

## Checks panel

| Scenario | `test-verification` |
|----------|---------------------|
| Section empty / incomplete | Action required or Failure |
| All items valid | Success |
| Includes skip/na with valid reasons | Success (disputes listed in check output for reviewers) |

## Merge

Requires **`verified`** + **`test-verification`** success + reviews/CI.
