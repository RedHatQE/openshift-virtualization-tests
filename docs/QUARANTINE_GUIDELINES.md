# OpenShift Virtualization Test Stability, Quarantine and De-quarantine Guidelines

## Introduction

This document establishes mandatory procedures for achieving and maintaining dependable **GREEN** test lanes for OpenShift Virtualization Tests (AKA: tier2).

**Why This Matters:**
- Unreliable test results hinder continuous delivery
- Manual investigation wastes significant QE time
- Reduced capacity for new feature development and automation
- Mistrust in test results causes release delays

**Goal**: Enhance testing efficiency and reliability while maintaining full test coverage and high product quality.

## Current Challenges

- **Inconsistent test results**: Uncertainty and delays in release decisions
- **Repeated lane failures**: Block continuous delivery and release schedules
- **Manual investigation overhead**: Time spent determining if failures are bugs or test instability
- **Manual verification burden**: Time on manual testing instead of new automation
- **Troubleshooting waste**: Chasing intermittent issues consumes resources

## Milestone and Branch Management

### Y-Stream (`main` Branch) - EXTRA CAUTION REQUIRED

**For `main` branch (upcoming y-stream release), quarantining requires EXTRA CARE until Code Freeze (CF).**

- Product code may contain bugs until CF
- Stabilization period expected between Feature Freeze and Blockers Only phase
- Extra inspection is needed for ALL quarantine decisions
- Handle test failures with care. Distinguish between product bugs and test issues

### Z-Stream - GREEN Expectation

Z-stream lanes **MUST BE GREEN**:
- No new major features should be introduced
- No API changes should be introduced
- Any failures are likely regressions requiring immediate attention

## Workflow for GREEN Lanes

### Step 1: Review Process

**MANDATORY**: Conduct a review of all failing tests across different lanes until all are GREEN.

**Review checklist:**
- [ ] Identify all failing tests in all lanes
- [ ] Group failures by test or pattern
- [ ] Check for known issues in Jira
- [ ] Analyze new failures immediately

### Step 2: Test Failure Analysis (TFA)

For each failure, determine the root cause category and take appropriate action.
Make sure to:
- Be specific about what failed and why
- Avoid generic messages like "Test failed" or "Assertion error"
- If a product bug was opened, link to the bug in the analysis message

#### Category 1: Product Bug

**Identification**: Failure is due to an actual product defect.

**Actions:**
- Open a bug in Jira with the appropriate priority (and a fix version if not opened on the next y-stream release).
- Use `pytest_jira` integration to skip test conditionally when bug is open.  If needed, use `is_jira_open` for conditional skip.

Conditional skip for product bug:

```python
import pytest

@pytest.mark.jira("CNV-12345", run=False)  # Skips if the bug is open
def test_feature_a():
    pass
```

#### Category 2: Automation Issue

**Identification**: Failure is due to test code or test framework issue.

**Actions:**
- Open a task in Jira under the team's backlog
- **Manual Verification MANDATORY**: Verify that the scenario passes manually before marking analysis as complete
  Manual verification is needed to make sure the tested feature does work as expected before quarantining the test.
- Include ALL failure analysis information and logs in Jira

Quarantine for automation issue:

Apply pytest's `xfail` marker with `run=False`, for example:

```python
import pytest
from utilities.constants import QUARANTINED


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: VM is going into running state which it shouldn't, CNV-123",
    run=False,
)
def test_my_failing_test():
    ...
```

**Benefit**: Provides pytest summary insights:

```text
1 deselected, 2 passed, 1 quarantined, ...
```

**Jira Requirements:**
- Title starts with `[stabilization]`
- Labels: `quarantined-test`
- Priority based on test importance
- Complete failure analysis documentation
- List any specific actions that should be taken when working on de-quarantining the test
- If backport is needed, make sure to add the info in the ticket

#### Category 3: System / Environment Issue

**Identification**: Failure is due to infrastructure, environment, or external dependencies.

**Actions:**
- **CANNOT QUARANTINE** - Open a ticket to devops
- **Manual Verification MANDATORY**: Verify that the scenario passes manually before marking analysis as complete
- Perform additional analysis

**Additional Analysis Required:**
1. Can the failure be avoided by running test on specific hardware?
2. Can the failure be caught during cluster sanity checks?
3. Open an issue to update cluster sanity to include environment requirements that prevent this failure

**System Issue Examples:**
- Artifactory connection problems
- Network infrastructure issues
- Resource constraints

### Step 3: Quarantine Decision

Determine if a test requires quarantine is based on:
- Failure is not a product bug
- Repeated failures (twice or more in the past 10 runs)
- Root cause requiring extended analysis
- Tests should be migrated between tiers (e.g., tier2 → tier1)
- Automation issue that cannot be fixed immediately

- **Gating test failures** - As gating tests have higher priority, they should be fixed as soon as possible

### When NOT to Quarantine

**DO NOT quarantine**:
- **System issues** - Based on your analysis, open a ticket to DevOps
- **Automation blockers** - Tests that MUST be executed before a release (use blocker tickets instead)

### Blocker Tickets vs. Quarantine

Understanding this distinction is critical:

| Aspect             | Blocker Tickets                         | Quarantine                                     |
|--------------------|-----------------------------------------|------------------------------------------------|
| **Use Case**       | Tests MUST run before release           | Automation issues, can be temporarily disabled |
| **Urgency**        | Fix immediately (within current sprint) | Fix based on priority (may be future sprint)   |
| **Release Impact** | Blocks release until resolved           | Does not block release                         |
| **Tracking**       | Blocker bug in Jira                     | Task with `xfail` marker                       |
| **Fix Timeline**   | Current sprint                          | Based on priority                              |

### Implementation

**Tools:**
- `pytest.mark.xfail` - For quarantine marking
- `pytest_jira` - For conditional skipping when bugs are open
- `pytest-repeat` - For stability verification (de-quarantine)

### Pull Request Requirements

When submitting quarantine PR:

- **Title**: Must start with `Quarantine:`
- **Description**: Include a link to Jira ticket and brief explanation
- **Backporting**: If needed, make sure to backport the quarantine PR to other branches.

**GitHub Label**: `quarantine` label will be added automatically


## De-Quarantine and Re-inclusion Process

- De-quarantine work must be included in each sprint based on tests priority

### Re-inclusion Criteria

Tests can **ONLY** be re-included after demonstrating stability:
- Test must be verified in Jenkins on a cluster identical (as much as possible) to the one where the failure occurred
- **25 consecutive successful runs via Jenkins** using `pytest-repeat`
- Number can be adjusted based on test flakiness, characteristics and risk; this must be discussed within the sig

**Local Verification Command:**
```bash
pytest --repeat-scope=session --count=25 <path to test module>
```

### De-Quarantine Checklist

Complete ALL items before re-including test:

- [ ] Root cause identified and fixed
- [ ] Test fix implemented and verified locally
- [ ] **Assert messages enhanced** with meaningful information from original failure - if needed
- [ ] `xfail` marker removed from test
- [ ] Jenkins verification passes (by default: 25 consecutive runs)

Once the PR is merged:
- [ ] The test is included in an active test lane
- [ ] Jira ticket updated with:
  - [ ] Root cause explanation
  - [ ] Fix description
  - [ ] Verification results
  - [ ] Closed with appropriate resolution
- [ ] If the fix needs to be backported to other branches, each backport PR must be verified using the same verification process
