<!-- To be used with https://github.com/myk-org/rootcoz
Complements the main analysis prompt — history-aware classification.
-->

# Pre-Classification Check: Did a Previous Test Break the Cluster?

## MANDATORY: Before classifying any failure, answer this question first:

**Did an earlier test in this job run modify cluster resources and fail to clean them up?**

If yes → the current failure is likely a side effect of that earlier test's failed
teardown, not an independent issue.

## How to Check

1. **Scan the console log for teardown failures BEFORE the current test.**
   Look for:
   - `TimeoutExpiredError` during teardown or fixture cleanup
   - `ERROR` in teardown/finalizer of a preceding test
   - `teardown_module`, `teardown_class`, or fixture `yield` cleanup failures

2. **Identify what the failed teardown was supposed to revert.**
   Look for any test that patches, modifies, or reconfigures cluster-scoped resources:
   operators, subscriptions, CRDs, node labels/taints, network configurations, or
   cluster-level CRs (HyperConverged, KubeVirt, NetworkAddonsConfig, etc.).
   If the teardown of such a test failed, the cluster may be left in a modified state.

3. **Check if the current failure matches the expected impact.**
   For example: pods stuck in Pending, operators degraded, nodes not schedulable,
   feature gates in wrong state, network policies broken — any symptom consistent
   with the resource that was not reverted.

## Classification

- **The test whose teardown failed**: Classify based on why its teardown failed —
  CODE ISSUE if the cleanup logic is wrong, PRODUCT BUG if the product blocked
  the revert, INFRASTRUCTURE if an environmental issue (node outage, storage
  failure, etc.) prevented cleanup.
- **All other tests that failed after it**: Use the **same classification** as the
  root-cause test. In the reason, state: "Caused by [test_name] teardown failure —
  [resource] was not reverted."

## When This Check Does NOT Apply

- The current test is the **first failure** in the run
- No teardown errors appear before the current test in the console log
- The failure has a clearly independent root cause (e.g., wrong assertion value,
  import error, syntax error)
- The failure occurs during **pytest collection** (e.g., `ModuleNotFoundError`,
  `SyntaxError`, missing fixture) — collection happens before any test runs
- The cluster was already broken **before any test ran** (e.g., deployment failure,
  cluster not provisioned, operators not installed)
- The failure is in a completely **unrelated area** to what the previous test modified
  (e.g., previous test changed storage config, current test fails on CPU topology)
- The same failure pattern appears in **previous job runs** where no teardown failure
  preceded it — this indicates a recurring issue independent of teardown cascades

In these cases, proceed with normal classification rules.
