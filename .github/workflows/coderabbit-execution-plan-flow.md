> *This document was created with the assistance of Claude (Anthropic).*

# CodeRabbit Test Execution Plan Workflow - Complete Flow Reference

Automated workflow for managing complete test execution plan lifecycle with CodeRabbit AI code reviewer.

## Quick Start

### Request a Test Plan
```bash
/generate-execution-plan    # Team members only
/verified                   # Team members only
```

### Respond to Test Plan
```bash
@coderabbitai I've added the tests as suggested  # Anyone, any commit
/verified                   # Team members only
```

---

## Overview

This workflow orchestrates an iterative review cycle between PR authors and CodeRabbit to ensure comprehensive test coverage. It automatically tracks status through labels and manages the complete verification lifecycle.

**Key Features:**
- 🤖 Automatic label management
- 👥 Team member privileges (bypass commit restrictions)
- 🔄 Complete lifecycle tracking
- ⚙️ Auto-helper: `/verified` triggers plan generation if none exists
- 🧹 Auto-cleanup on new commits

---

## Labels Used

| Label | Meaning | How to Get | How to Remove |
|-------|---------|-----------|---------------|
| **execution-plan-generated** | CodeRabbit posted test plan, awaiting review | CodeRabbit posts plan | CodeRabbit verifies or new commit |
| **execution-plan-passed** | Test plan verified and approved | CodeRabbit posts "verified" | New commit |

---

## Complete Flow Tables

### Flow 1: Test Plan Generation (`/generate-execution-plan`)

| User Type | Commit Location | Label State | Result | Final Label |
|-----------|----------------|-------------|--------|-------------|
| Team member | Any commit | None | ✅ Requests plan | plan-generated (after CodeRabbit posts) |
| Team member | Any commit | plan-generated | ✅ Requests NEW plan | plan-generated |
| Non-member | Any commit | None | ❌ **Blocked (silent)** | None |
| Non-member | Any commit | plan-generated | ❌ **Blocked (silent)** | plan-generated (stays) |

**Note:** Both `/generate-execution-plan` and `/verified` are **restricted to team members only**. Non-members should use `@coderabbitai` to respond to test plans.

---

### Flow 2: `/verified` Command (No Plan Exists - Auto-Helper)

| User Type | Commit Location | Label State | Result | Final Label |
|-----------|----------------|-------------|--------|-------------|
| Team member | Any commit | None | ✅ Auto-requests plan | plan-generated (after CodeRabbit posts) |
| Non-member | Any commit | None | ❌ **Blocked (silent)** | None |

**Note:** When no label exists, `/verified` automatically triggers plan generation (convenience feature). **Team members only.**

---

### Flow 3: `/verified` Command (Plan Exists - Review Mode)

| User Type | Commit Location | Label State | Result | Final Label |
|-----------|----------------|-------------|--------|-------------|
| Team member | Any commit | plan-generated | ✅ Asks CodeRabbit to review | plan-generated (stays) |
| Non-member | Any commit | plan-generated | ❌ **Blocked (silent)** | plan-generated (stays) |

**Note:** When label exists, `/verified` means "review my response". **Team members only.**

---

### Flow 4: User Responds with Keywords

| Trigger | User Type | Label State | Commit Restriction | Result |
|---------|-----------|-------------|-------------------|--------|
| @coderabbitai | Any | plan-generated | ✅ None (any commit) | Asks CodeRabbit to review |
| "test execution plan" | Any | plan-generated | ✅ None (any commit) | Asks CodeRabbit to review |
| Any comment | Any | None | N/A | ❌ No action |

**Note:** Keyword-based responses have **no commit restrictions**.

---

### Flow 5: CodeRabbit Actions

| CodeRabbit Posts | Current Label | Result | Final Label |
|------------------|---------------|--------|-------------|
| "Test Execution Plan" | None | ✅ Adds label | plan-generated |
| "Test Execution Plan" | plan-generated | ✅ No-op | plan-generated |
| "test execution plan verified" | plan-generated | ✅ Updates labels | plan-passed |
| "TEST EXECUTION PLAN VERIFIED" | plan-generated | ✅ Updates (case-insensitive) | plan-passed |

**Note:** Detection is **case-insensitive**.

---

### Flow 6: System Events

| Event | Current Label | Result | Notification |
|-------|--------------|--------|--------------|
| New commit pushed | plan-generated | ✅ Removes | Silent |
| New commit pushed | plan-passed | ✅ Removes | Silent |
| New commit pushed | None | No-op | Silent |

**Note:** Automatic cleanup on new commits. Plan must be regenerated.

---

### Flow 7: Edge Cases

| Trigger | Context | Label State | Result | Feedback |
|---------|---------|-------------|--------|----------|
| Any command | Issue (not PR) | Any | ❌ Gracefully skipped | Silent |
| renovate[bot] comment | PR | Any | ❌ Ignored | Silent |
| User response | PR | Both labels exist | ❌ CodeRabbit NOT triggered | Silent |
| Manual label add/remove | N/A | Any | No workflow impact | Silent |

**Note:** All jobs validate PR context. Bot comments are ignored. If both `execution-plan-generated` and `execution-plan-passed` labels exist simultaneously (invalid state), CodeRabbit review requests are blocked.

---

## Complete State Diagram

```
     None (No labels)
          │
          ├─── /generate-execution-plan ──┐
          │                                │
          ├─── /verified (auto) ───────────┤
          │                                │
          ▼                                ▼
    CodeRabbit receives ──► Posts plan ──► plan-generated
                                                │
                                                ├─── User responds
                                                │
                                                ├─── /verified
                                                │
                                                ▼
                                      CodeRabbit reviews
                                                │
                            ┌───────────────────┴───────────────┐
                            │                                   │
                            ▼                                   ▼
                     Needs changes                      Posts "verified"
                            │                                   │
                            └─────────┐                        ▼
                                      │                  plan-passed
                                      │                        │
      ┌───────────────────────────────┴────────────────────────┤
      │                                                         │
      ├─── New commit ────────────────────────────────────────┤
      │                                                         │
      ▼                                                         ▼
    None ◄───────────────────────────────────────────────────┘
```

---

## Job Summary

**Single consolidated job:** `manage-execution-plan`

This job dynamically routes to the appropriate scenario based on event context:

| Scenario | Trigger | Function |
|----------|---------|----------|
| 1 | New commit pushed | Remove labels (reset workflow) |
| 2 | CodeRabbit posts "test execution plan" | Add plan-generated label |
| 2 | CodeRabbit posts "verified" | Update to plan-passed label |
| 3 | `/generate-execution-plan` or `/verified` (team only) | Request plan |
| 4 | User responds (when label exists) | Ask CodeRabbit to review |

**Note:** All scenarios run within a single workflow job for cleaner PR UI (1 check instead of 5).

---

## Command Reference

| Command | When to Use | Who Can Use | Commit Restriction | Action |
|---------|-------------|-------------|-------------------|--------|
| `/generate-execution-plan` | Request new plan | **Team members only** | ✅ None (any commit) | Requests plan |
| `/verified` (no label) | Shortcut to request plan | **Team members only** | ✅ None (any commit) | Auto-requests plan |
| `/verified` (with label) | Confirm/respond to plan | **Team members only** | ✅ None (any commit) | Asks review |
| @coderabbitai | Respond to plan | **Anyone** | ✅ None (any commit) | Asks review |

---

## Permission Matrix

| Action | Team Member | Non-member |
|--------|-------------|------------|
| `/generate-execution-plan` | ✅ Any commit | ❌ Blocked |
| `/verified` (no label) | ✅ Any commit | ❌ Blocked |
| `/verified` (with label) | ✅ Any commit | ❌ Blocked |
| @coderabbitai | ✅ Any commit | ✅ Any commit |

---

## Complete Lifecycle Example

```
1. Developer pushes code changes
   ↓
2. Developer comments: /verified or /generate-execution-plan (team members only)
   → /generate-execution-plan: team members only
   → /verified: team members only
   → Non-members: use @coderabbitai instead
   ↓
3. Workflow requests test plan from CodeRabbit
   ↓
4. CodeRabbit posts test execution plan
   → Label 'execution-plan-generated' added automatically
   ↓
5. Developer reviews plan and responds:
   Option A: Comments @coderabbitai with response
   Option B: Comments /verified on last commit
   Option C: Comments about "test execution plan"
   → Workflow asks CodeRabbit to review response
   ↓
6. CodeRabbit reviews response:

   Path A - Needs Changes:
   ├─ CodeRabbit provides feedback
   └─ Back to step 5

   Path B - Satisfied:
   ├─ CodeRabbit posts "Test execution plan verified"
   ├─ Label 'execution-plan-generated' removed
   ├─ Label 'execution-plan-passed' added
   └─ Review complete! ✅
   ↓
7. Developer pushes new commit
   → Both labels removed automatically
   → Cycle restarts if needed
```

---

## What CodeRabbit Expects

### For Test Plan
CodeRabbit will post a review comment with test execution plan in this format:
```
**Test Execution Plan**

- path/to/test_file.py
- path/to/test_file.py::TestClass::test_method
- -m marker_name
```

### For Verification
To complete the cycle, CodeRabbit must post this exact phrase (case-insensitive):
```
Test execution plan verified
```

### For Changes
CodeRabbit provides specific feedback:
- Missing test scenarios
- Additional test paths needed
- Specific markers or fixtures to verify

---

## Troubleshooting

### Label not added after CodeRabbit response?
- ✅ Verify CodeRabbit's comment contains: "Test Execution Plan" (case-insensitive)
- ✅ Check workflow run logs in Actions tab

### CodeRabbit not responding to comments?
- ✅ Ensure `execution-plan-generated` label is present (for review requests)
- ✅ Check command triggers:
  - `/generate-execution-plan` (team members only)
  - `/verified` (team members only)
  - `@coderabbitai` (anyone, always works)
  - "test execution plan" (anyone, always works)

### Initial plan not requested?
- ✅ Both `/verified` and `/generate-execution-plan`: **Team members only** (non-members blocked)
- ✅ Non-members: Use `@coderabbitai` to respond instead
- ✅ Check workflow run logs in Actions tab

### `/verified` not working?
**Check these common issues:**
1. **Team member?** Required - non-members are blocked
2. **Label exists?** Triggers review request
3. **No label?** Auto-requests plan - convenience feature
4. **Not a team member?** Use `@coderabbitai` instead

### Labels not removed on new commit?
- ✅ Check that `pull_request_target` with `synchronize` event is enabled
- ✅ Verify BOT3_TOKEN has correct permissions

### Review cycle stuck?
- ✅ Check if CodeRabbit used exact phrase: "Test execution plan verified" (case-insensitive)
- ✅ Manual fix: Remove `execution-plan-generated`, add `execution-plan-passed` via GitHub UI

### Both labels exist simultaneously?
**This is an invalid state.** If both `execution-plan-generated` and `execution-plan-passed` labels exist:
- ✅ CodeRabbit will NOT be triggered (workflow protection)
- ✅ Manual fix: Remove one of the labels via GitHub UI
  - If plan is verified: Remove `execution-plan-generated`, keep `execution-plan-passed`
  - If plan is still pending: Remove `execution-plan-passed`, keep `execution-plan-generated`

### Silent failure (no feedback)?
**This is by design for:**
- Non-members using `/verified` or `/generate-execution-plan` (blocked)
- Both labels existing simultaneously (invalid state - see above)
- Comments on issues (not PRs) - gracefully skipped
- Bot comments (renovate) - ignored

**To get feedback:**
- Team members: Use `/generate-execution-plan` or `/verified` on any commit
- Non-members: Use `@coderabbitai` keyword (or request team access)

---

## Workflow Files

- **Main workflow:** `.github/workflows/request-coderabbit-test-instructions.yml`
- **Documentation:** `.github/workflows/coderabbit-execution-plan-flow.md` (this file)

---

## Key Improvements (Fixed in Latest Version)

✅ **Simplified permission model** - `/verified` is now team members only (no "last commit" exceptions)
✅ **Fixed review.body handling** - Commands work in both comments and review submissions
✅ **Extracted helper function** - Eliminated duplicate team membership checks
✅ **Consolidated workflow** - Single job instead of 5 separate jobs (cleaner PR UI)
✅ **Case-insensitive matching** - Works with any capitalization
✅ **PR context validation** - Gracefully handles non-PR contexts
✅ **Auto-helper feature** - `/verified` auto-requests plan if none exists (team members only)
✅ **Consistent PR number extraction** - Robust error handling

---

## Monitoring

### Active Reviews
Filter PRs by label: `execution-plan-generated`

### Completed Reviews
Filter PRs by label: `execution-plan-passed`

### Team Members
Members of `cnvqe-bot` team can use both `/generate-execution-plan` and `/verified` commands. Non-members must use `@coderabbitai` to interact with the workflow.
