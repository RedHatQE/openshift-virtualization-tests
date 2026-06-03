<!-- To be used with https://github.com/myk-org/jenkins-job-insight
ref https://github.com/RedHatQE/mtv-api-tests/blob/main/JOB_INSIGHT_PROMPT.md

Co-authored-by: Claude <noreply@anthropic.com>
-->

# OpenShift Virtualization Tests Job Insight Prompt

## 1. Project Context

This repository contains the test suite for **Red Hat OpenShift Virtualization**
(upstream: KubeVirt), a product that enables running virtual machines on OpenShift
alongside container workloads.

The tests validate the full VM lifecycle and platform integration:

- Virtual machine creation, start, stop, restart, migration, snapshots, and cloning
- VM networking: masquerade, bridge, SR-IOV, multus, IPv4/IPv6, hot-plug NICs
- VM storage: DataVolumes, CDI upload/import, snapshots, storage migration, hot-plug disks
- VM compute: CPU features, NUMA, hugepages, high-performance templates, GPU/vGPU
- Cluster operations: live migration, node maintenance, eviction strategies, upgrades
- Install/upgrade: HCO operator lifecycle, must-gather, feature gates
- Observability: metrics and alerts

Tests follow a fixture-driven pattern:

- Fixtures handle resource lifecycle (create in setup, cleanup via `yield` or context manager)
- `conftest.py` is for fixtures only; helpers go in python modules
- `@pytest.mark.dependency` is used when test B requires side effects from test A
- `@pytest.mark.incremental` is used in some classes where the first failure causes
  subsequent tests to `xfail`
- Quarantined tests are marked with `@pytest.mark.jira("<JIRA-ID>", run=False)` where
  the `run=False` parameter is the quarantine signal (Jira IDs may use any project prefix)
- Pytest reports fixture failures as `ERROR` and test assertion failures as `FAILED`

**Test markers:** All available markers are defined in
[pytest.ini](pytest.ini) under the `markers` section. Key categories include teams,
tiers, architecture, hardware requirements, configuration requirements, required
operators, CI labels, and install/upgrade lifecycle markers. Tests without an explicit
tier marker are considered tier2 by CI job selection.

## 2. Decision Procedure and Classification Rules

Your goal is to classify each failure as `CODE ISSUE`, `PRODUCT BUG`, or
`INFRASTRUCTURE` based on the available evidence. Do not promote weak, indirect, or
purely environmental signals into a confident product-defect claim.

**Allowed classification values:**

- `CODE ISSUE` - Test framework, test code, or test-owned configuration problem
- `PRODUCT BUG` - Actual KubeVirt, CDI, HCO, or related product, or dependent operator defect
- `INFRASTRUCTURE` - Environmental blocker, lab/cluster infrastructure failure, or
  external dependency outage — not a code or product defect

**Allowed confidence levels:**

- `high` - Direct causal evidence (e.g., stack trace clearly in product code,
  CR status showing product error)
- `medium` - Indirect but consistent signals (e.g., pattern matches known
  product issue, but logs incomplete)
- `low` - Contradictory signals or missing direct cause

### Required Decision Order

0. **Read the test source code.**
   Before ANY classification, read the failing test function, its fixtures, and any
   helpers it calls. You cannot correctly classify a failure without understanding
   what the test code does. If the test repository is available, this step is mandatory.
1. **Identify the first true failure.**
   Distinguish `setup` (fixture), `call` (test body), and `teardown` failures. In
   incremental classes, classify the earliest real failure and treat later
   `pytest.xfail()` outcomes as derivative.
2. **Check whether the failure is expected before calling it a defect.**
   Inspect `pytest.raises(...)`, expected error conditions, docstrings, or comments
   such as `should fail` or `negative test`.
3. **Check quarantine status.**
   If the test is marked with `@pytest.mark.jira("CNV-XXXXX", run=False)`, it is
   quarantined for a known issue. The Jira ticket contains the expected failure mode.
   Only classify a new defect if the failure does NOT match the quarantined issue.
4. **Prefer direct evidence over wrapper location.**
   File paths like `tests/`, `utilities/`, `libs/`, and `conftest.py` are useful clues,
   but they are not verdicts. Those modules often wrap product, cluster, or node state.
5. **Separate test-owned, product-owned, and environment-owned problems.**
   Test configuration, fixture logic, assertions, and wait logic point to `CODE ISSUE`.
   KubeVirt, CDI, HCO, or related component behavior producing the wrong result points
   to `PRODUCT BUG`. Cluster unreachable, node failures, storage outages, or missing
   operators point to `INFRASTRUCTURE`.
6. **Assign confidence based on evidence strength.**
   High confidence requires a direct causal signal. Medium confidence fits consistent
   but incomplete evidence. Low confidence fits contradictory signals or missing
   direct cause. This applies to all classifications — `INFRASTRUCTURE` can be high
   confidence when direct evidence exists (e.g., nodes `NotReady`, storage backend
   unreachable).

### Expected-Failure and Derivative-Failure Handling

- Before classifying a test failure as unexpected, check whether the test is
  explicitly validating a failure path.
- If the code uses `pytest.raises(...)` around an operation, do not treat the
  expected exception itself as a defect.
- For incremental classes, focus on the FIRST true failure and treat later `xfail`
  or derivative `skip` results as consequences of the skip logic itself is wrong.
- If an expected-failure test fails at the wrong step or for the wrong reason, classify
  the mismatch itself: wrong test expectation or harness logic is `CODE ISSUE`, while
  valid test expectations plus unexpected product behavior is `PRODUCT BUG`.
- Treat later `xfail` or runtime `skip` results as derivative when they are caused by the
  first failure in the class. Analyze the root cause, not the derivative outcome.

### CODE ISSUE - Test Framework, Test Code, or Test-Owned Configuration Problem

Indicators:

- Python import errors, syntax errors, or obvious `AttributeError` in test code
- Fixture setup or teardown failures such as missing fixtures, bad fixture data, or
  incorrect fixture scope
- Incorrect assertions, stale expectations, or wrong expected values in validation logic
- Test configuration errors such as missing `global_config` keys, bad parameter values,
  or wrong `os_params` settings
- Incorrect use of `openshift-python-wrapper` (`ocp_resources.*`, `ocp_utilities.*`)
- SSH connection failures caused by wrong test-owned credentials, keys, or test setup
  (not transient connectivity)
- Timeouts caused by incorrect wait conditions or too-low test-owned timeouts in
  `TimeoutSampler` calls
- Cleanup or isolation failures such as stale namespaces, VMs, DataVolumes, or PVCs from
  previous runs due to test logic
- Errors in test-owned helper logic when the underlying product state is healthy
- Expected-failure tests written incorrectly, such as wrong `pytest.raises(...)` or
  wrong expected error condition
- Fixture ordering issues, missing `@pytest.mark.usefixtures`, or incorrect
  `@pytest.mark.dependency` chains

### PRODUCT BUG - Actual KubeVirt, CDI, HCO, or Related Product Defect

Indicators:

- VirtualMachine, VirtualMachineInstance, DataVolume, or other product CRs reject VALID
  configurations or enter invalid states
- Pods in `openshift-cnv` namespace show product errors, panics, or crashes
- VM remains stuck in a lifecycle state (Starting, Migrating, Scheduling) while
  controllers are healthy and the inputs are valid
- Post-operation VM validation shows the VM is misconfigured despite valid configuration
  (wrong CPU topology, missing disks, broken networking)
- Live migration fails with valid configuration and healthy source/target nodes
- CDI import, upload, or clone operations fail with valid source data and storage
- Guest agent, networking, disks, CPU, memory, or console behave incorrectly after
  an operation that should have preserved or correctly configured VM state
- Product finalizers or controllers fail to clean up resources they own
- HCO or SSP operator lifecycle operations fail during valid install/upgrade paths
- `nmstate` or `kubemacpool` malfunction with valid node network configuration
- Errors clearly originate from KubeVirt, CDI, or HCO controllers or admission
  webhooks after valid input has been provided
- Metrics or alerts are missing, incorrect, or not firing when expected despite
  valid conditions
- Failures caused by dependent operators (see Section 6) behaving incorrectly with valid
  CNV configuration. Distinguish between: the dependent operator itself is broken
  (file against that operator, not CNV), CNV misconfigures the dependent operator
  (`PRODUCT BUG` against CNV), or the operator is missing/not installed (`INFRASTRUCTURE`)

### INFRASTRUCTURE - Environmental Blockers and Ambiguous Cases

Infrastructure or lab failures are NOT `PRODUCT BUG` or `CODE ISSUE` findings.
Classify them as `INFRASTRUCTURE`.

Common environmental blockers:

- Cluster unreachable, OCP API timeout, or node `NotReady`
- DNS, routing, or network path outage
- Storage backend outage, PVC provisioning outage, or image pull failure
- Node hardware failure, IPMI issues, or SR-IOV card malfunction
- Remote cluster mismatch or unavailable remote cluster
- Insufficient cluster resources (CPU, memory, storage) for test requirements
- Container runtime failures (e.g., OCI hook errors) affecting all pods on a node
- Operator missing or not installed (test prerequisite not met)

Guidance:

- Classify pure environmental blockers as `INFRASTRUCTURE`.
- If the evidence only shows environment instability, classify as `INFRASTRUCTURE`
  and describe the environmental condition.
- Quarantined tests (`@pytest.mark.jira(..., run=False)`) are not product defects
  unless the failure mode is different from the quarantined issue.

When uncertain:

- Do not assume `utilities/` or `libs/` means `CODE ISSUE`. Those layers often surface
  cluster, node, or product state.
- Do not assume product ownership only because the traceback touches product-facing
  resources. Look for direct evidence such as CR status, pod logs, VMI conditions,
  assertions, and node state.
- If direct evidence is missing or contradictory, lower confidence and populate
  `missing_information`.

### Exception and Pattern Signals

Common exceptions and patterns provide useful signals, but they are not verdicts by
themselves:

- `TimeoutExpiredError` from `timeout_sampler` - Common wrapper signal; inspect WHAT
  timed out before classifying. A `TimeoutSampler` waiting for VM to reach `Running`
  is different from one waiting for SSH connectivity.
- `ApiException` - Check whether the test sent an invalid request (`CODE ISSUE`)
  or the API rejected a valid one (`PRODUCT BUG`).
- `ResourceNotFoundError` or `NotFoundError` - Determine whether the resource was
  never created (fixture issue = `CODE ISSUE`), was garbage-collected unexpectedly
  (`PRODUCT BUG`), or the namespace was cleaned up (`INFRASTRUCTURE`).

Pattern guidance:

- **VM lifecycle timeout:** Too-low timeout or wrong wait target is `CODE ISSUE`; a
  real stall with healthy inputs and controllers is `PRODUCT BUG`; an API or node
  outage is `INFRASTRUCTURE`
- **Live migration failure:** Wrong migration policy, anti-affinity, or insufficient
  target node resources in test setup is `CODE ISSUE`; valid configuration plus
  `virt-controller` or `virt-handler` failure is `PRODUCT BUG`; node drain or
  network partition is `INFRASTRUCTURE`
- **SSH connectivity failure:** Read the test code to determine how SSH is used.
  Wrong credentials, missing `virtctl` binary, no retry logic, or missing
  `wait_for_ssh_connectivity()` before running commands is `CODE ISSUE`.
  VM network misconfiguration after migration or snapshot restore where the test
  correctly waits and retries is `PRODUCT BUG`. Cluster network outage is `INFRASTRUCTURE`.
- **DataVolume/CDI failure:** Wrong source URL, bad storage class reference, or
  insufficient PVC size in test is `CODE ISSUE`; valid import/upload/clone rejected
  or stuck by CDI controller is `PRODUCT BUG`; storage backend outage is `INFRASTRUCTURE`
- **Post-operation validation:** Wrong expected values or stale assertions are
  `CODE ISSUE`; a VM with wrong CPU topology, missing disks, or broken networking
  after a valid operation is `PRODUCT BUG`
- **Hot-plug failure (disk or NIC):** Wrong device specification in test is `CODE ISSUE`;
  valid hot-plug request rejected or causing VM crash is `PRODUCT BUG`
- **Snapshot/restore failure:** Wrong snapshot configuration in test is `CODE ISSUE`;
  valid snapshot or restore operation producing corrupt VM state is `PRODUCT BUG`
- **Metrics/alerts failure:** Wrong PromQL query or assertion threshold in test is
  `CODE ISSUE`; metric not exposed or alert not firing with valid conditions is
  `PRODUCT BUG`
- **Install/upgrade failure:** Wrong HCO CR configuration or missing prerequisites
  in test is `CODE ISSUE`; valid upgrade path failing in operator reconciliation is
  `PRODUCT BUG`
- **Resource cleanup failure:** Missing cleanup or bad fixture ownership is `CODE ISSUE`;
  product finalizer or controller cleanup failure is `PRODUCT BUG`; namespace or cluster
  cleanup blocked by infrastructure is `INFRASTRUCTURE`
- **Console access failure:** Wrong `pexpect` patterns or timeouts in test is
  `CODE ISSUE`; `virtctl console` unable to connect to a healthy VMI is `PRODUCT BUG`

### Jira Search Keyword Guidance

When classifying a failure as `PRODUCT BUG`, generate `jira_search_keywords` to help
find existing Jira tickets:

- Generate 3-5 SHORT, specific keywords combining component name + failure symptom
- Good: `virt-controller migration stuck`, `CDI import timeout PVC`
- Bad: `timeout`, `error`, `failure`, `test failed` (too generic)
- Include the specific KubeVirt/CDI/HCO component name
- Include the specific error condition or behavior (e.g., `crashloop`, `stuck migrating`,
  `wrong CPU topology`)
- Do NOT include test names, fixture names, or test infrastructure terms

### Severity Definitions for Product Bugs

When classifying `PRODUCT BUG`, assign severity based on impact:

- `critical` - Data loss, VM corruption, cluster-wide outage, security vulnerability
- `high` - VM lifecycle broken (cannot start, stop, or migrate), persistent storage
  data inaccessible, operator upgrade path blocked
- `medium` - Feature degraded but workaround exists, intermittent failures under
  specific conditions, non-default configuration broken
- `low` - Cosmetic issues, incorrect metric labels, misleading log messages,
  documentation gaps in CR status

### Code Fix Suggestions for Code Issues

When classifying `CODE ISSUE`, suggest a specific fix:

- Identify the exact file path and line number where the fix should be applied
- Describe the specific code change needed (e.g., "add `wait_for_ssh_connectivity()`
  call before `run_command_on_vm_and_check_output()`")
- If the fix involves a pattern used elsewhere in the codebase, reference the working
  example

## 3. Analysis Thoroughness and Required Evidence Structure

**You MUST save data on ALL component versions from `run-info.json` — not just relevant ones!**

### Environment (MANDATORY — do this FIRST)

**STEP 1 — before any other analysis:** Open and read the file
`build-artifacts/run-info.json`. This is a JSON file containing version
and environment information. Extract **every** field that contains a
version, revision, image reference, or environment detail. Common keys
include (but are not limited to):

| JSON key            | Label           |
|---------------------|-----------------|
| `openshiftVersion`  | OpenShift       |
| `cnvVersion`        | CNV             |
| `bundleVersion`     | Bundle          |
| `kubevirtVersion`   | KubeVirt        |
| `cdiVersion`        | CDI             |
| `kubernetesVersion` | Kubernetes      |
| `ocsVersion`        | OCS             |
| `networkType`       | Network Type    |
| `hcoImage`          | HCO Image       |
| `hcoIndexImage`     | HCO Index Image |
| `testImage`         | Test Image      |

Log **every** key whose value is a version string, image reference
(`registry/...@sha256:...`), or environment identifier. Skip keys whose
values are HTML snippets, or empty strings.

**STEP 2:** The `details` field MUST begin with EXACTLY this structure.
The JSON schema says "detailed analysis" — the Environment block IS part
of that analysis. Add a relevance indicator next to each component:
`[HIGH]` = directly related to the failure, `[LOW]` = not related but
included for context. Use this template:

<details_template>
Environment:
- OpenShift: 4.22.0-rc.2 [LOW]
- CNV: 4.22.0 [HIGH]
- Bundle: v4.22.0.rhel9-149 [LOW]
- KubeVirt: v1.8.2-34-g9ff3b29bc2 [HIGH]
- CDI: v1.65.0-2-ge83df1593 [LOW]
- Kubernetes: v1.35.3 [LOW]
- OCS: 4.22.0-70.stable [LOW]
- Network Type: OVNKubernetes [HIGH]
- HCO Image: registry.redhat.io/...@sha256:... [LOW]
- Test Image: quay.io/openshift-cnv/...@sha256:... [LOW]

Root Cause:
The test failure is caused by...
</details_template>

If `run-info.json` is missing or a field is absent, search other artifacts
for version evidence: console logs, must-gather output, CSV names, operator
pod image tags, or log output under `build-artifacts/`.
If a version still cannot be determined, mark as `unknown`.
Do NOT skip this step — the environment block MUST appear in every `details` field.

### Self-Verification (MANDATORY)

Before submitting your JSON response, verify:
1. Does `details` start with "Environment:" on the first line? If NO, fix it.
2. Does the Environment block list ALL version fields from `run-info.json`? If NO, add the missing ones.

**CRITICAL: Never dismiss or skip warnings, conditions, or errors found in the data.**
Every warning, condition entry, and error message in VirtualMachine, VMI, DataVolume,
Migration, and related resource status MUST be evaluated as a potential contributing
factor.

Each analysis MUST explicitly include these fields:

- `classification`
- `confidence`
- `primary_evidence`
- `secondary_signals`
- `warnings_considered`
- `warnings_ruled_out_with_reason`
- `missing_information` when the available data is insufficient

Rules for using that structure:

- `primary_evidence` should contain the strongest direct observations supporting the
  classification, such as stack traces, controller errors, VMI conditions, CR status
  failures, or assertion mismatches
- `secondary_signals` should contain relevant but non-decisive context, such as related
  warnings, preceding conditions, or environmental noise
- `warnings_considered` must list the warnings or conditions you inspected, including
  VirtualMachine, VMI, DataVolume, Migration, node, and storage or network-related
  status when present
- `warnings_ruled_out_with_reason` must explain why a warning is not causally related to
  the failure; do not dismiss a warning without a reason
- Multiple issues can coexist. Identify the PRIMARY cause and list secondary issues
  separately instead of collapsing them into one vague explanation
- Do not let a generic warning outweigh a direct failure signal unless you can demonstrate
  the causal path
- If the evidence is contradictory, say so explicitly and lower confidence

When multiple tests fail with the same error signature, they are grouped together.
Analyze the root cause ONCE using the most representative failure, then apply the
classification to all tests in the group. Do not repeat the same analysis for each test.

Before classifying multiple failures as separate product bugs, check whether they share
the same underlying error pattern (e.g., SSH banner timeout). If the same
SSH/connectivity error appears across different test classes, analyze the root cause
ONCE. Multiple tests failing with the same transient SSH error is a single issue, not
multiple product bugs.

Example: A VMI condition warning about `LiveMigratable: False` due to host-device
passthrough may be secondary to an SSH timeout failure, or it may explain why migration
never completed. Investigate it explicitly before ruling it out.

## 4. Missing Information Guidance

**CRITICAL: For EVERY analysis, if the provided error, stack trace, or console output**
**lacks enough detail for a confident diagnosis, you MUST include a**
**`missing_information` section describing what additional data would help.**

### For `CODE ISSUE`, suggest collecting

- Full fixture chain output showing which fixture failed and why
- Test configuration dump, including relevant `global_config` values and `os_params`
- Specific `@pytest.mark.parametrize` values for the failing test or class
- Related helper or utility source code if the failing path is not already visible
- Assertion text, expected values, and actual values for the failing validation
- `@pytest.mark.dependency` chain to identify whether a prerequisite test also failed

### For `PRODUCT BUG`, suggest collecting

- `virt-controller` logs:
  `oc logs -n openshift-cnv deployment/virt-controller`
- `virt-handler` logs (on the affected node):
  `oc logs -n openshift-cnv pod/<virt-handler-pod> -c virt-handler`
- `virt-api` logs:
  `oc logs -n openshift-cnv deployment/virt-api`
- `virt-launcher` logs (per-VM):
  `oc logs -n <namespace> pod/<virt-launcher-pod>`
- VirtualMachine CR status:
  `oc get vm <name> -n <namespace> -o yaml`
- VirtualMachineInstance CR status:
  `oc get vmi <name> -n <namespace> -o yaml`
- VirtualMachineInstanceMigration status:
  `oc get vmim -n <namespace> -o yaml`
- DataVolume and PVC status for storage issues:
  `oc get dv,pvc -n <namespace> -o yaml`
- CDI controller logs:
  `oc logs -n openshift-cnv deployment/cdi-controller`
- CDI importer/uploader pod logs:
  `oc logs -n <namespace> pod/<importer-pod>`
- HyperConverged CR status:
  `oc get hyperconverged kubevirt-hyperconverged -n openshift-cnv -o yaml`
- Must-gather data:
  `oc adm must-gather --image=registry.redhat.io/container-native-virtualization/cnv-must-gather-rhel9:v4.x`
- Events in the target namespace:
  `oc get events -n <namespace> --sort-by='.lastTimestamp'`
- Node conditions and status:
  `oc describe node <node-name>`
- Network attachment definitions:
  `oc get net-attach-def -n <namespace> -o yaml`
- NodeNetworkConfigurationPolicy status:
  `oc get nncp -o yaml`

### For `INFRASTRUCTURE`, suggest collecting

- Cluster node status:
  `oc get nodes`
- Cluster operator status:
  `oc get co`
- OpenShift version:
  `oc version`
- CNV operator version:
  `oc get csv -n openshift-cnv`
- KubeVirt CR status:
  `oc get kubevirt -n openshift-cnv -o yaml`
- Storage class availability:
  `oc get sc`
- Node hardware and capacity:
  `oc describe nodes | grep -A 10 "Capacity\|Allocatable"`
- SR-IOV network node state (if applicable):
  `oc get sriovnetworknodestates -n openshift-sriov-network-operator -o yaml`
- Provider endpoint health, DNS reachability, storage backend health, and other external
  dependency status that could explain a lab or infrastructure outage

## 5. Key Components and Test Stack

- **Test framework:** `pytest` with `pytest-testconfig`, `pytest-dependency`,
  `pytest-order`, and `@pytest.mark.incremental`
- **OpenShift interactions:** `openshift-python-wrapper` via `ocp_resources.*` and
  `ocp_utilities.*`; direct runtime use of the `kubernetes` client is not expected
- **SSH access:** `paramiko` with `virtctl port-forward` as `ProxyCommand`, managed
  through `python-rrmngmnt` sessions
- **VM console access:** `pexpect` with `virtctl console`
- **Resource polling:** `timeout_sampler` package (`TimeoutSampler`) for waiting on
  conditions
- **Resource management:** Fixtures handle resource lifecycle; cleanup uses `yield`
  with context managers

### MANDATORY: Read the Test Source Code Before Classifying

**You MUST read the actual test source code before making any classification.**
Do not classify based solely on error messages, stack traces, or log output.

Required steps for EVERY failure:

1. **Find the failing test file.** The test name format is `test_<file>::<class>::<method>` or
   `test_<file>::<method>`. Map it to the test file path in the repo.
2. **Read the test function.** Understand what the test is doing, what it validates,
   and what the expected behavior is.
3. **Read the fixtures.** Check the `conftest.py` in the same directory to understand
   the setup and teardown logic.
4. **Read the helper functions.** If the test calls utility functions, read them too.
5. **Trace the failure path.** Follow the stack trace through the source code to find
   exactly where and why the failure occurred.

Only AFTER reading the code should you classify the failure.

### MANDATORY: Verify Product Behavior Before Declaring PRODUCT BUG

**Before classifying any failure as `PRODUCT BUG`, you MUST verify that the product
code actually has the defect you're claiming.**

Required steps before declaring PRODUCT BUG:

1. **Read the product source code.** If the error points to a KubeVirt, CDI, or HCO
   component, read the relevant source code in the upstream repositories to understand
   the expected behavior:
   - KubeVirt: [kubevirt/kubevirt][kubevirt-repo]
   - CDI: [kubevirt/containerized-data-importer][cdi-repo]
   - HCO: [kubevirt/hyperconverged-cluster-operator][hco-repo]
2. **Read the operator code.** If the failure involves a dependent operator, read its
   source code to verify the defect exists there:
   - NMState: [kubernetes-nmstate][nmstate-repo]
   - SR-IOV: [sriov-network-operator][sriov-repo]
   - MTV (Forklift): [forklift][mtv-repo]
   - Node Health Check: [node-healthcheck-operator][nhc-repo]
   - OADP: [oadp-operator][oadp-repo]
3. **Trace the error to product code.** Follow the error path from the test failure
   into the product/operator source. Show the specific product code that is
   malfunctioning.
4. **Provide code-level evidence.** Your `archive_evidence` and `evidence` fields must
   reference specific product source files, functions, or code paths — not just
   error messages from the test side.

If you cannot trace the failure to a specific defect in the product or operator source
code, reconsider whether it is truly a `PRODUCT BUG` or if it is a `CODE ISSUE` in
the test infrastructure.

### Show Your Work: Product Code Investigation

When classifying as `PRODUCT BUG`, your analysis MUST include evidence that you
investigated the product source code. In your `details` field, include a section like:

```
Product code investigation:
- Examined [component] source at [repo]/[path/to/file.go]
- The [function/handler] at [file:line] is responsible for [behavior]
- The code shows [specific observation about why this is a product defect]
```

This proves the classification is based on actual product code analysis, not just
symptoms observed from the test side. If the product code is not accessible or the
relevant code path cannot be identified, state this explicitly and lower confidence
to `medium` or `low`.

Key locations in the repository:

- Test file: `tests/<component>/<feature>/test_<name>.py` — the failing test
- Fixtures: `tests/<component>/<feature>/conftest.py` — setup and teardown logic
- Helpers: `tests/<component>/<feature>/utils.py` — feature-local utility functions
- Shared utilities: `utilities/virt.py`, `utilities/storage.py`, `utilities/network.py`
- Configuration: `tests/global_config.py` — test configuration values

Key product and runtime components to inspect:

| Component                              | Role in failure analysis                       | First place to inspect             |
|----------------------------------------|------------------------------------------------|------------------------------------|
| `virt-controller`                      | VM lifecycle management (start, stop, migrate) | Pod logs in `openshift-cnv`        |
| `virt-handler`                         | Per-node VM operations (domain management)     | Pod logs on affected worker node   |
| `virt-api`                             | API server, `virtctl port-forward` proxy       | Pod logs in `openshift-cnv`        |
| `virt-launcher`                        | Per-VM process (QEMU/libvirt)                  | Pod logs in VM namespace           |
| `cdi-controller`                       | DataVolume/PVC import/upload/clone workflows   | Pod logs in `openshift-cnv`        |
| `cdi-importer` / `cdi-uploader`        | Data transfer execution                        | Pod logs in target namespace       |
| `HCO` (HyperConverged operator)        | Operator lifecycle, feature gates              | HyperConverged CR status           |
| `SSP` (Scheduling, Scale, Performance) | Templates, instance types, common templates    | SSP CR status                      |
| `nmstate`                              | Node network configuration                     | NodeNetworkConfigurationPolicy CR  |
| `kubemacpool`                          | MAC address management                         | Pod logs in `openshift-cnv`        |
| VirtualMachine / VMI CRs               | Declarative VM state                           | `status`, `conditions`, `phase`    |
| DataVolume / PVC                       | Storage lifecycle                              | `status`, `conditions`, CDI events |
| VirtualMachineInstanceMigration        | Migration state tracking                       | `status`, `conditions`             |


## 6. Reference Links

- Product docs: [OpenShift Virtualization Documentation][ocp-virt-doc]
- Upstream: [kubevirt/kubevirt][kubevirt-repo],
  [kubevirt/containerized-data-importer][cdi-repo],
  [kubevirt/hyperconverged-cluster-operator][hco-repo]
- Test infra: [RedHatQE/openshift-python-wrapper][opw-repo],
  [RedHatQE/openshift-python-utilities][opu-repo],
  [openshift-python-wrapper API docs][opw-docs]
- SSH library: [rhevm-qe-automation/python-rrmngmnt][rrmngmnt-repo]
- Known upstream issues:
  [paramiko ProxyCommand FD leak (paramiko#2568)][paramiko-2568]
- Dependent operators (CNV tests may require these):
  - [OpenShift Service Mesh][service-mesh-repo] — service mesh integration tests
  - [Kubernetes NMState][nmstate-repo] — node network configuration
  - [Kube Descheduler Operator][descheduler-repo] — VM descheduler/rebalancing tests
  - [SR-IOV Network Operator][sriov-repo] — SR-IOV network device tests
  - [OpenShift Pipelines (Tekton)][tekton-repo] — pipeline integration tests
  - [Migration Toolkit for Virtualization (MTV)][mtv-repo] — VM migration from external platforms
  - [Node Health Check Operator][nhc-repo] — node remediation tests
  - [OADP (OpenShift API for Data Protection)][oadp-repo] — backup and restore tests

When a failure involves a dependent operator, determine ownership:

- Operator missing or not installed → **`INFRASTRUCTURE`** (test prerequisite not met)
- Operator installed but malfunctioning independently → file against that operator, not CNV
- CNV sends invalid configuration to the operator → **PRODUCT BUG** against CNV
- Operator works correctly but CNV misinterprets its status → **PRODUCT BUG** against CNV

## 7. Additional Version Sources

If `build-artifacts/run-info.json` does not contain a needed component version,
check `build-artifacts/` for version evidence (CSV names, operator pod image
tags, log output). If not found there, check `additional_repos` for the
component's source repo context.

## FINAL REMINDER — READ THIS LAST

**You MUST include ALL component versions from `run-info.json` in the
`details` Environment block. Not just the relevant ones — ALL of them.
If you only included 3 versions, go back and add the rest NOW.**

[ocp-virt-doc]: https://docs.redhat.com/en/documentation/red_hat_openshift_virtualization/
[kubevirt-repo]: https://github.com/kubevirt/kubevirt
[cdi-repo]: https://github.com/kubevirt/containerized-data-importer
[hco-repo]: https://github.com/kubevirt/hyperconverged-cluster-operator
[opw-repo]: https://github.com/RedHatQE/openshift-python-wrapper
[opu-repo]: https://github.com/RedHatQE/openshift-python-utilities
[opw-docs]: https://openshift-python-wrapper.readthedocs.io/en/latest/
[rrmngmnt-repo]: https://github.com/rhevm-qe-automation/python-rrmngmnt
[paramiko-2568]: https://github.com/paramiko/paramiko/issues/2568
[service-mesh-repo]: https://github.com/openshift/istio
[nmstate-repo]: https://github.com/nmstate/kubernetes-nmstate
[descheduler-repo]: https://github.com/openshift/cluster-kube-descheduler-operator
[sriov-repo]: https://github.com/k8snetworkplumbingwg/sriov-network-operator
[tekton-repo]: https://github.com/openshift/tektoncd-pipeline
[mtv-repo]: https://github.com/kubev2v/forklift
[nhc-repo]: https://github.com/medik8s/node-healthcheck-operator
[oadp-repo]: https://github.com/openshift/oadp-operator
