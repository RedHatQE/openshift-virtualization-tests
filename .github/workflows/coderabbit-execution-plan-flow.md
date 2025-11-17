# Generated using Claude cli
# CodeRabbit Test Execution Plan Workflow

Automated workflow for managing complete test execution plan lifecycle with CodeRabbit AI code reviewer.

## Overview

This workflow orchestrates an iterative review cycle between PR authors and CodeRabbit to ensure comprehensive test coverage for code changes. It automatically tracks the status of test execution plans through labels and manages the complete verification lifecycle.

## Labels Used

- **`execution-plan-generated`** - CodeRabbit has provided a test execution plan (auto-applied)
- **`execution-plan-passed`** - CodeRabbit has verified the test plan is complete (auto-applied)

## Workflow Triggers

### 1. Test Plan Generation
**Triggers:**
- User comments `/generate-execution-plan`
- User comments `/verified` (but NOT `/verified cancel`)

**Validation:**
- For `/verified` comments: Must be on the last commit of the PR (review comments only)
- Team membership check: Excludes users in `cnvqe-bot` team

**Result:**
- Workflow requests CodeRabbit to create test execution plan
- When CodeRabbit posts comment containing "Test Execution Plan"
- → Auto-adds `execution-plan-generated` label

### 2. Review Request (when execution-plan-generated label exists)
**Triggers (any of):**
- User comments `/generate-execution-plan`
- User comments `/verified` (must be on last commit for review comments)
- User posts comment containing:
  - `test execution plan`
  - `@coderabbitai`

**Validation:**
- Only triggers if `execution-plan-generated` label is present
- For `/verified` comments: Must be on the last commit of the PR (review comments only)

**Result:**
- Prompts CodeRabbit to review user's response
- CodeRabbit either:
  - **Verifies:** Posts "Test execution plan verified" → Labels updated automatically
  - **Requests changes:** Provides specific feedback → Cycle continues

### 3. Plan Verification Complete
**Trigger:** CodeRabbit posts comment containing "Test execution plan verified"

**Result:**
- Removes `execution-plan-generated` label
- Adds `execution-plan-passed` label
- Review cycle complete

### 4. Label Reset on New Commits
**Trigger:** New commit pushed to PR (`synchronize` event)

**Result:**
- Removes both `execution-plan-generated` and `execution-plan-passed` labels
- Test plan must be regenerated for new code changes

## Complete Lifecycle Example

```
1. User comments /generate-execution-plan OR /verified (on last commit)
   ↓
2. CodeRabbit posts test execution plan review comment
   → 'execution-plan-generated' label auto-added
   ↓
3. User responds to test plan (options):
   - Comments @coderabbitai with response
   - Comments /verified on last commit (review comment)
   - Comments /generate-execution-plan for re-review
   → CodeRabbit prompted to review response
   ↓
4. CodeRabbit reviews:
   ├─ Needs changes → Provides feedback → Back to step 3
   └─ Satisfied → Posts "Test execution plan verified"
      → 'execution-plan-generated' removed
      → 'execution-plan-passed' added
   ↓
5. New commit pushed
   → Both labels removed automatically
   → Back to step 1
```

## User Actions

### To Request Initial Test Plan

**Option 1: Request execution plan**
```bash
/generate-execution-plan
```

**Option 2: Mark as verified (must be on last commit)**
```bash
/verified
# Must be a review comment on the last commit
# For issue comments, can be used anytime
```

### To Respond to Test Plan or Request Re-review

**Option 1: Request plan regeneration/re-review**
```
/generate-execution-plan
```

**Option 2: Direct response with @mention**
```
@coderabbitai I've added tests for the new authentication flow in tests/test_auth.py
```

**Option 3: Mark as verified after testing (must be on last commit)**
```
/verified
Tested on environment X with the following scenarios:
- Scenario 1
- Scenario 2
```
**Note:** `/verified` on review comments must be on the last commit of the PR

### What CodeRabbit Expects

**For Verification:**
CodeRabbit must post this exact phrase to complete the cycle:
```
Test execution plan verified
```

**For Changes:**
CodeRabbit provides specific feedback with:
- Missing test scenarios
- Additional test paths needed
- Specific test markers or fixtures to verify

## Workflow Architecture

This is a consolidated single workflow that handles:
- Initial test plan requests (`/generate-execution-plan` or `/verified`)
- Test plan detection and labeling
- User response review requests
- Plan verification and label updates
- Label cleanup on new commits

## Monitoring

### Active Review Cycles
PRs with `execution-plan-generated` label have active test plan reviews in progress.

### Completed Reviews
PRs with `execution-plan-passed` label have verified test execution plans.

### Stale Plans (Optional)
Uncomment the schedule trigger in the workflow to enable daily monitoring:
- Checks for PRs with `execution-plan-generated` label older than 3 days
- Posts reminder comments automatically

## Workflow Files

- **Consolidated workflow:** `.github/workflows/coderabbit-test-execution-plan.yml`
- **Documentation:** `.github/workflows/coderabbit-execution-plan-flow.md` (this file)

## Troubleshooting

**Label not added after CodeRabbit response?**
- Verify CodeRabbit's comment contains exact text: "Test Execution Plan"
- Check workflow run logs in Actions tab

**CodeRabbit not responding to user comments?**
- Ensure `execution-plan-generated` label is present
- Comment must contain trigger phrases:
  - `/generate-execution-plan` (request new/updated plan)
  - `@coderabbitai` (direct mention)
  - `/verified` (mark as ready, but NOT `/verified cancel`)
  - `test execution plan` (discussion about the plan)
- For `/verified` on review comments: Must be on the last commit
- Avoid using `/verified cancel` which is explicitly excluded

**Initial plan not requested?**
- Check if user is in `cnvqe-bot` team (team members are excluded)
- For `/verified` commands: Review comment must be on the last commit
- Verify command was `/generate-execution-plan` or `/verified` (not `/verified cancel`)
- Check workflow run logs in Actions tab

**Labels not removed on new commit?**
- Check that `pull_request_target` with `synchronize` event is enabled
- Verify BOT3_TOKEN has correct permissions

**Review cycle stuck?**
- Check if CodeRabbit used exact phrase "Test execution plan verified"
- Manual label management: Remove `execution-plan-generated` and add `execution-plan-passed` if needed
