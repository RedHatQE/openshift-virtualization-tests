# Openshift-virtualization-tests Test plan

## **Clone and Storage Migration support for VMState PVC - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** KubeVirt VEP 312 (enhancements PR 313); clone implementation PR 16634; declarative implementation PR 19173.
- **Feature Tracking:** VIRTSTRAT-482 — Improve scalability of VMState storage.
- **Epic Tracking:** CNV-79308 — Clone and Storage Migration support for VMState PVC.
- **Feature Maturity:**
  - DP: KubeVirt v1.10 Alpha target [confirm]
  - TP: N/A
  - GA: CNV v5.1.0 [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** sig-storage
- **Participating SIGs:** sig-compute-migrations, downstream Storage Ecosystem QE

**Document Conventions (if applicable):**

- **VM state storage:** Persistent storage used for supported TPM, EFI, or CBT state.
- **Owned state storage:** Storage created from the VM's declarative template and deleted with the VM.
- **Adopted state storage:** Existing user-managed storage referenced by a VM and retained after VM deletion.

### **Feature Overview**

This feature lets a VM owner explicitly create or reuse persistent VM state storage so cloning, templating, recreation, and migration can preserve supported guest state. It removes dependence on an implicit, difficult-to-discover volume while retaining the existing implicit behavior for users who do not opt in. The design is Alpha for KubeVirt v1.10, and the downstream release target remains subject to confirmation. This plan focuses on user-visible clone and storage-migration outcomes and the safety boundaries around ownership, concurrent use, and cleanup.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:* CNV-79308 requires VM cloning and storage migration to support VM state storage; VEP 312 defines generated, adopted, and combined storage workflows.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* VM owners and platform operators can discover, provision, move, clone, and recover persistent guest state using declarative workflows.
  - *List the customer use cases identified:* Clone a VM with preserved trust state; migrate state to supported storage; recreate a VM from existing state; manage VM resources through GitOps; retain legacy implicit behavior.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:* Downstream GA timing is not confirmed, and the implementation PRs are not merged; execution must use the final supported build and storage matrix.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:* A supported VM clone starts with usable VM state; supported storage migration moves or reuses VM state as designed without losing guest state; unsupported combinations fail safely and visibly.
  - *Note any gaps or missing criteria:* Jira does not define the complete storage access-mode matrix, exact user-facing failure text, or release graduation criteria.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:* Security — prevent two running VMs from using the same state storage; Usability — expose clear status for the active state volume and blocked operations; Compatibility — preserve implicit behavior and already-created declarative VMs when the Alpha gate is disabled; Documentation — update release notes and existing caveats.
  - *Note any NFRs not covered and why:* Performance and scale have no Jira target; monitoring adds no new metric or alert requirement; UI work is not identified; portability is limited to supported filesystem storage classes.

#### **2. Known Limitations**

- **Alpha availability:** The declarative workflow is gated and targeted for KubeVirt v1.10 Alpha; Beta and GA are not defined in the VEP.
  - *Sign-off:* [Name/Date]
- **Single state volume:** One VM state volume is supported per VM; multiple state volumes are not a design goal.
  - *Sign-off:* [Name/Date]
- **Source-only RWO live migration:** An adopted RWO state volume without a creation template cannot support live migration because destination state storage cannot be created; the VM can still start and use a cold path.
  - *Sign-off:* [Name/Date]
- **No automatic conversion:** Existing VMs are not automatically converted from implicit state storage to the declarative workflow.
  - *Sign-off:* [Name/Date]
- **Open related defect:** CNV-83112 tracks a cross-product migration that can leave persistent state on source storage.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [x] **Developer Handoff**
  - *Details:* Merged VEP 312 and the open implementation PRs were reviewed; a final handoff is still required after implementation stabilizes.
- [x] **Technology Challenges**
  - *Details:* State must remain usable across VM identity changes, generated and user-owned storage need different cleanup behavior, and access mode changes migration behavior.
- [x] **API Extensions**
  - *Details:* Users receive an opt-in declarative VM state field plus status identifying the active state volume; invalid or unsafe combinations are rejected or blocked with an observable reason.
- [x] **Test Environment Needs**
  - *Details:* Testing needs supported RWO and RWX filesystem storage classes, a guest configuration that persists TPM or EFI state, and at least two schedulable nodes for live migration.
- [x] **Topology Considerations**
  - *Details:* Focused lifecycle checks run on a standard multi-node cluster; live migration requires two schedulable workers and storage reachable from the applicable source and destination nodes.

---

### **II. Software Test Plan (STP)**

#### **1. Scope of Testing**

**Testing Goals**

- **[P0] Preserve state through cloning:** Verify a clone of a supported VM starts independently with the expected persistent TPM or EFI state.
- **[P0] Preserve state through storage migration:** Verify supported RWO and RWX migration paths maintain guest state and expose the correct active storage after completion.
- **[P0] Fail safely for unsupported migration:** Verify source-only RWO live migration is blocked before state is lost and the source VM remains usable.
- **[P0] Prevent unsafe concurrent use:** Verify a second running VM cannot adopt state storage held by another running VM.
- **[P1] Enforce storage ownership:** Verify owned storage is cleaned up with its VM while adopted storage remains user-managed.
- **[P1] Preserve compatibility:** Verify legacy implicit state behavior continues when the Alpha workflow is introduced or disabled.
- **[P2] Validate recovery boundaries:** Verify interrupted or rejected operations do not report success with an unusable VM.

**Out of Scope (Testing Scope Exclusions)**

- **Performance and large-scale concurrency**
  - *Rationale:* Jira and the VEP define no latency, throughput, or scale target for this Alpha feature.
  - *PM/Lead Agreement:* [Name/Date]
- **Automatic conversion of existing VMs**
  - *Rationale:* The VEP explicitly lists automatic migration to the declarative workflow as a non-goal.
  - *PM/Lead Agreement:* [Name/Date]
- **Multiple VM state volumes per VM**
  - *Rationale:* The design supports one state volume and identifies multiple volumes as a non-goal.
  - *PM/Lead Agreement:* [Name/Date]
- **Cross-product migration-tool implementation**
  - *Rationale:* CNV-83112 is retained as regression context, but its product-specific remediation is outside this epic's implementation scope.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- Final execution cannot begin until PR 16634 and PR 19173 are merged into a consumable downstream build.
  - *Sign-off:* [Name/Date]
- Exact event, condition, and error wording may change before the draft implementation stabilizes; assertions will use the approved user-visible contract.
  - *Sign-off:* [Name/Date]
- RWO and RWX coverage requires compatible filesystem storage classes and sufficient cluster capacity for migration.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validate generated, adopted, clone, migration, ownership, validation, and cleanup behavior from the VM owner's perspective.
  - *Details:* Cover the two Jira acceptance criteria plus the safety boundaries required by the merged design.
- [x] **Automation Testing** — Automate stable Tier 1 and Tier 2 scenarios in the downstream virtualization test repository.
  - *Details:* Extend the existing clone and storage-migration suites rather than create a disconnected framework.
- [x] **Regression Testing** — Run existing clone, storage migration, rollback, cleanup, persistent TPM, and encrypted-guest coverage.
  - *Details:* Existing coverage remains regression evidence and is not duplicated in Section III.
- [ ] **Self-Validation Testing** — Do not add Alpha, storage-intensive migration workflows to the fast self-validation package.
  - *Details:* Revisit after the feature is enabled by default and the focused lifecycle test proves stable.

**Non-Functional**

- [ ] **Performance Testing** — No performance objective is defined.
  - *Details:* Record functional duration only for troubleshooting; do not create a release threshold.
- [ ] **Scale Testing** — No scale objective is defined.
  - *Details:* Concurrent VM or migration scale remains outside the Alpha acceptance criteria.
- [x] **Security Testing** — Validate exclusive use of persistent state and safe reuse after the holder stops.
  - *Details:* Confirm one running VM cannot consume state owned by another running VM.
- [x] **Usability Testing** — Validate discoverable active storage and clear feedback for blocked or invalid operations.
  - *Details:* Users must be able to distinguish success, waiting, rejection, and unsupported migration.
- [ ] **Monitoring** — No new metric or alert requirement is defined.
  - *Details:* Existing events and status are validated as user feedback; no monitoring scenario is added.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Cover RWO and RWX filesystem storage, generated and adopted storage, and implicit legacy behavior.
  - *Details:* Use only supported storage combinations from the final downstream release.
- [x] **Upgrade Testing** — Validate that existing implicit VMs remain usable and existing declarative VMs remain manageable when the Alpha gate changes state.
  - *Details:* No automatic conversion is expected.
- [x] **Dependencies** — Gate execution on merged implementation, a downstream build, and supported storage classes.
  - *Details:* The Storage Ecosystem and compute-migration owners must confirm the final matrix.
- [x] **Cross Integrations** — Regress clone, snapshot or restore, backup, migration, TPM, EFI, and CBT workflows affected by persistent state handling.
  - *Details:* Product-specific migration-tool behavior is reported separately.

**Infrastructure**

- [ ] **Cloud Testing** — No provider-specific behavior is introduced.
  - *Details:* Run on any supported platform that supplies the required RWO and RWX filesystem storage classes.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node cluster with at least two schedulable workers.
- **OCP & OpenShift Virtualization Version(s):** Downstream build containing the merged feature; CNV v5.1.0 target [confirm].
- **CPU Virtualization:** Hardware virtualization enabled on worker nodes.
- **Compute Resources:** Capacity for two concurrent VM instances during clone or migration validation.
- **Special Hardware:** N/A; no device passthrough is required.
- **Storage:** Supported RWO and RWX filesystem storage classes with source and destination capacity.
- **Network:** Stable cluster and guest connectivity sufficient to verify a user-visible workload marker.
- **Required Operators:** OpenShift Virtualization and storage operators healthy.
- **Platform:** A supported platform with two-node migration capability.
- **Special Configurations:** Declarative VM state Alpha gate enabled for feature scenarios and disabled for compatibility coverage.

#### **3.1. Testing Tools & Frameworks**

- VM and volume status inspection to verify the active state storage and user-visible blocked conditions.
- Guest-level TPM or EFI state marker to verify persistence across clone, restart, recreation, and migration.
- Storage inventory inspection to verify ownership, destination placement, retention, and cleanup.

#### **4. Entry Criteria**

- [ ] Requirements and the merged VEP are approved and stable.
- [ ] Clone and declarative implementation PRs are merged into the target build.
- [ ] Supported RWO and RWX storage classes are documented and available.
- [ ] A guest configuration can create observable persistent TPM or EFI state.
- [ ] Expected status and failure behavior is approved for unsupported or conflicting use.
- [ ] Existing clone and storage-migration regression suites pass on the target build.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Open implementation PRs may miss the downstream release integration window.
  - **Mitigation:** Keep automation changes isolated behind feature availability and execute manual acceptance checks on candidate builds.
  - *Estimated impact on schedule:* Final automation and sign-off may move to a later build or release.
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Existing suites cover clone, migration, and persistent state separately but may miss ownership combinations introduced by the declarative workflow.
  - **Mitigation:** Add focused source-only, template-only, combined, RWO, and RWX scenarios before approval.
  - *Areas with reduced coverage:* Unapproved storage drivers and large-scale concurrency.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** A cluster may not provide both supported RWO and RWX filesystem storage classes.
  - **Mitigation:** Reserve a migration-capable storage environment and run unsupported combinations only as explicit negative checks.
  - *Missing resources or infrastructure:* A second supported storage class or two schedulable workers.
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Exact failure messages and downstream graduation behavior cannot be frozen while PR 19173 remains a draft.
  - **Mitigation:** Validate stable user outcomes first and update text assertions after the implementation contract is approved.
  - *Alternative validation approach:* Manual review of status and events on each candidate build.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** Storage migration and encrypted-guest validation consume shared cluster time and storage capacity.
  - **Mitigation:** Keep focused validation in regular lanes and schedule full Tier 2 matrices in a dedicated migration-capable lane.
  - *Current capacity gaps:* Dedicated time for the full RWO and RWX matrix.
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Testing depends on compatible clone, VM lifecycle, storage, and migration deliverables landing together.
  - **Mitigation:** Gate execution on merged commits and publish the tested build and storage matrix in the result.
  - *Dependent teams or components:* Storage Ecosystem, clone or restore owners, and compute-migration owners.
  - *Sign-off:* [Name/Date]

**Other**

- **Risk:** Jira's statement that PR 19173 is merged may cause premature readiness assumptions.
  - **Mitigation:** Treat GitHub state as authoritative and re-check both implementation PRs before execution.
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

- **[CNV-79308]** — As a VM owner, I want a cloned VM to retain supported persistent trust state so that the clone is independently usable.
  - **TS-001**
  - *Test Scenario:* [Tier 2] Clone a VM with declarative state storage and verify the clone starts with preserved TPM or EFI state while the source remains usable
  - *Priority:* P0
- **[CNV-79308]** — As a VM owner, I want cloned state storage to be independent so that deleting one VM does not corrupt the other.
  - **TS-002**
  - *Test Scenario:* [Tier 2] Delete the source or clone in turn and verify the remaining VM retains its persistent state
  - *Priority:* P0
- **[CNV-79308]** — As a VM owner, I want unsafe simultaneous state reuse blocked so that two running VMs cannot modify the same trust state.
  - **TS-003**
  - *Test Scenario:* [Tier 1] Start a second VM from state storage held by a running VM and verify security isolation with a clear blocked result without modifying the holder
  - *Priority:* P0
- **[CNV-79308]** — As a VM owner, I want to reuse adopted state after the original VM stops so that planned recreation preserves state.
  - **TS-004**
  - *Test Scenario:* [Tier 1] Stop the holding VM, start a replacement from the adopted state storage, and verify the saved TPM or EFI state is available
  - *Priority:* P1
- **[CNV-79308]** — As a cluster administrator, I want RWO VM state to move to target storage so that storage migration preserves the complete VM.
  - **TS-005**
  - *Test Scenario:* [Tier 2] Migrate a VM using adopted RWO state plus a creation template and verify state continuity, target storage placement, and active-volume status
  - *Priority:* P0
- **[CNV-79308]** — As a cluster administrator, I want successful RWO migration to clean up replaced owned storage so that obsolete volumes do not remain allocated.
  - **TS-006**
  - *Test Scenario:* [Tier 2] Complete RWO state migration and verify replaced owned storage is removed while user-owned source storage is retained
  - *Priority:* P1
- **[CNV-79308]** — As a cluster administrator, I want RWX VM state migration to preserve state without unnecessary replacement storage.
  - **TS-007**
  - *Test Scenario:* [Tier 2] Live migrate a VM using RWX state storage, sample guest state throughout the move, and verify the same active volume remains usable afterward
  - *Priority:* P0
- **[CNV-79308]** — As a cluster administrator, I want unsupported source-only RWO live migration blocked before data loss so that the source VM remains recoverable.
  - **TS-008**
  - *Test Scenario:* [Tier 2] Request live migration for source-only RWO state and verify migration is blocked with a clear reason while the source VM remains usable
  - *Priority:* P0
- **[CNV-79308]** — As a platform operator, I want invalid state storage definitions rejected so that unsupported resources are not created.
  - **TS-009**
  - *Test Scenario:* [Tier 1] Submit missing, non-filesystem, and fixed-name generated state definitions and verify each is rejected with actionable feedback
  - *Priority:* P1
- **[CNV-98256]** — As an existing VM owner, I want implicit persistent state behavior to remain compatible so that adopting the Alpha feature is optional.
  - **TS-010**
  - *Test Scenario:* [Tier 2] Start, restart, and migrate a legacy VM without declarative state configuration and verify its persistent state remains usable
  - *Priority:* P1
- **[CNV-98256]** — As a VM owner, I want a VM created with declarative state to remain manageable if the Alpha gate is later disabled.
  - **TS-011**
  - *Test Scenario:* [Tier 2] Disable new admission after creating a declarative-state VM and verify the existing VM can restart and retain state
  - *Priority:* P2

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

* **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name / @github-handle]
  - sig-storage representative: [Name / @github-handle]
  - sig-compute-migrations representative: [Name / @github-handle]
* **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name / @github-handle]
