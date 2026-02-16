# Openshift-virtualization-tests Test plan

## **Support Changing the VM Attached Network NAD Ref Using Hotplug - Quality Engineering Plan**

### **Metadata & Tracking**

| Field | Details |
|:------|:--------|
| **Enhancement(s)** | [VEP #140: Live Update NAD Reference](https://github.com/kubevirt/enhancements/blob/main/veps/sig-network/hotpluggable-nad-ref.md), [VEP Tracking Issue #140](https://github.com/kubevirt/enhancements/issues/140) |
| **Feature in Jira** | [CNV-72329](https://issues.redhat.com/browse/CNV-72329) |
| **Jira Tracking** | Epic: [CNV-72329](https://issues.redhat.com/browse/CNV-72329), Parent: [VIRTSTRAT-560](https://issues.redhat.com/browse/VIRTSTRAT-560) |
| **QE Owner(s)** | TBD |
| **Owning SIG** | sig-network |
| **Participating SIGs** | sig-network, sig-compute |
| **Current Status** | In Progress (Target: CNV v4.22.0) |

### **Related GitHub Pull Requests**

| PR Link | Repository | Source Jira Issue | Source Type | Description |
|:--------|:-----------|:------------------|:------------|:------------|
| [kubevirt/kubevirt#16412](https://github.com/kubevirt/kubevirt/pull/16412) | kubevirt/kubevirt | CNV-72329 | Epic | Implement Live Update of NAD Reference - adds feature gate LiveUpdateNADRef, VM controller NAD sync, migration evaluator for NAD changes, and e2e tests |

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability prior to formal test planning.

#### **1. Requirement & User Story Review Checklist**

| Check | Done | Details/Notes | Comments |
|:------|:-----|:--------------|:---------|
| **Review Requirements** | [x] | VEP #140 defines the ability to update the NAD reference (networkName) of a network on a running VM through Live Migration, gated by the LiveUpdateNADRef feature gate. The VM controller syncs NAD changes from VM spec to VMI spec and triggers automatic migration. | Requirements are well-defined in the VEP with clear scope boundaries. |
| **Understand Value** | [x] | Enables VM administrators to swap a VM's network connection (e.g., change VLAN ID) by referencing a different NetworkAttachmentDefinition without requiring a VM restart. This preserves workload continuity and maintains guest interface properties (MAC address, interface name). | High value for production environments where network maintenance windows must minimize downtime. |
| **Customer Use Cases** | [x] | Primary use case: Re-assign VMs to a new VLAN ID without rebooting. Secondary: Network maintenance operations requiring VM network reassignment across bridge-based secondary networks. | User story: "As a VM admin, I want to swap the guest's uplink from one network to another without the VM noticing." |
| **Testability** | [x] | Feature is testable through API-level operations (patching VM spec) and verifiable through network connectivity checks (ping), migration status verification, and VMI spec inspection. Requires a cluster with at least 2 schedulable nodes and bridge-based NADs. | Upstream e2e tests already exist in the PR covering positive, negative (non-existent NAD), and feature-gate-disabled scenarios. |
| **Acceptance Criteria** | [x] | (1) VM interfaces can be swapped between NADs without restart when feature gate is enabled. (2) NAD change triggers automatic live migration. (3) After migration, VM has connectivity on the new network. (4) Feature is gated behind LiveUpdateNADRef feature gate. (5) When feature gate is disabled, NAD changes do not trigger migration and VMI spec is not updated. | Criteria derived from VEP #140 goals and Jira acceptance criteria. |
| **Non-Functional Requirements (NFRs)** | [x] | No new scalability constraints introduced. Relies on existing KubeVirt migration infrastructure. No new update/rollback constraints. | Performance impact is limited to the migration itself, which uses existing infrastructure. |

#### **2. Technology and Design Review**

| Check | Done | Details/Notes | Comments |
|:------|:-----|:--------------|:---------|
| **Developer Handoff/QE Kickoff** | [ ] | PR #16412 is still under review. Key reviewers: orelmisan, EdDev, ormergi, fossedihelm, victortoso, 0xFelix. Branch: vep/nad-hotplug. | QE kickoff should be scheduled once PR is merged. |
| **Technology Challenges** | [x] | (1) Compatibility with Multus Dynamic Networks Controller (DNC) - the reconciliation logic must not patch the source pod's multus annotation when only the NAD reference changes, to avoid conflicts. (2) NAD name normalization - namespace-qualified vs. unqualified NAD names must be handled correctly. (3) Bridge binding is the only supported binding type for this feature. | Review comments flagged namespace-qualified NAD name comparison as a potential issue (sourcery-ai review). |
| **Test Environment Needs** | [x] | Minimum 2 schedulable worker nodes for live migration. Two distinct bridge-based NetworkAttachmentDefinitions (different VLANs or bridges). OVS or Linux bridge CNI plugin. KubeVirt configured with LiveMigrate workload update strategy and LiveUpdate VM rollout strategy. | Network infrastructure must support multiple bridge networks on the same node. |
| **API Extensions** | [x] | No new API fields. Existing field `spec.template.spec.networks[].multus.networkName` is now live-updatable when the feature gate is enabled. New feature gate: `LiveUpdateNADRef` (registered as Beta in v1.8). New cluster config method: `LiveUpdateNADRefEnabled()`. | The API surface is minimal - only the behavior of an existing field changes. |
| **Topology Considerations** | [x] | Feature requires live-migratable VMs. Non-migratable VMs cannot use this feature (explicit non-goal in VEP). Both source and target nodes must have the target NAD's underlying network infrastructure available. | Single-node clusters cannot use this feature since migration is required. |

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This test plan covers the LiveUpdateNADRef feature introduced by VEP #140, which allows changing the NetworkAttachmentDefinition (NAD) reference on a running VM's secondary network interface through live migration. Testing will validate the complete workflow from VM spec update through automatic migration to network connectivity verification on the target network.

**In Scope:**

- Feature gate (LiveUpdateNADRef) enable/disable behavior
- VM spec patching to change the NAD reference (networkName field)
- Automatic migration triggering when NAD reference changes
- Network connectivity verification after migration to the new NAD
- Loss of connectivity to the old network after migration
- VMI spec synchronization from VM spec (NAD reference propagation)
- Negative scenarios: non-existent NAD reference, migration failure handling
- Feature gate disabled behavior: no migration triggered, VMI spec unchanged
- RestartRequired condition logic when feature gate is enabled vs. disabled
- Bridge binding support verification
- Multiple NAD reference changes in sequence
- Interaction with existing NIC hotplug/unplug operations
- Interaction with VM rollout strategy configuration

#### **2. Testing Goals**

##### **Positive Use Cases (Happy Path)**

- Verify that changing the NAD reference on a running VM triggers automatic live migration when the LiveUpdateNADRef feature gate is enabled
- Verify that after migration completes, the VM has network connectivity on the new NAD (new VLAN/bridge)
- Verify that after migration, the VM loses connectivity to the old NAD network
- Verify that the VMI spec is updated with the new NAD reference after the change is applied
- Verify that the VM's guest interface properties (MAC address, interface name) are preserved across the NAD swap
- Verify that the RestartRequired condition is NOT set when only the NAD reference changes (with feature gate enabled)
- Verify that multiple sequential NAD reference changes each trigger a new migration and result in correct connectivity
- Verify that the feature works with namespace-qualified NAD names (e.g., `namespace/nad-name`)

##### **Negative Use Cases (Error Handling & Edge Cases)**

- Verify that changing the NAD reference to a non-existent NAD causes migration failure while the VMI spec is still updated
- Verify that when the LiveUpdateNADRef feature gate is disabled, changing the NAD reference does NOT trigger migration
- Verify that when the feature gate is disabled, the VMI spec is NOT updated with the new NAD reference
- Verify that attempting to change NAD reference on a non-migratable VM is handled correctly (RestartRequired condition)
- Verify behavior when the target NAD uses a different binding type (non-bridge) -- should not be supported
- Verify behavior when the target node does not have the required network infrastructure for the new NAD
- Verify that changing non-NAD network properties (e.g., network name field itself) still requires restart
- Verify behavior during an already in-progress migration when a NAD reference change is requested

#### **3. Non-Goals (Testing Scope Exclusions)**

| Non-Goal | Rationale | PM/Lead Agreement |
|:---------|:----------|:-------------------|
| Migrating between CNI types | Explicitly out of scope per VEP #140 | VEP-defined non-goal |
| Changing the network binding/plugin | Explicitly out of scope per VEP #140 | VEP-defined non-goal |
| Maintaining seamless network connectivity during migration | Explicitly out of scope per VEP #140; brief connectivity interruption during migration is expected | VEP-defined non-goal |
| Changing NAD reference on non-migratable VMs | Explicitly out of scope per VEP #140; requires DNC changes (Option 2) | VEP-defined non-goal |
| Changing the guest's network configuration after NAD swap | Guest-side IP reconfiguration is the user's responsibility | VEP-defined non-goal |
| In-place NAD swapping via Dynamic Networks Controller | Requires third-party component changes (DNC); current design uses migration approach | VEP design decision (Option 1 selected) |
| Performance benchmarking of migration speed | Migration performance is tested by existing migration test suites | Covered by existing tests |

#### **4. Test Strategy**

##### **A. Types of Testing**

| Item (Testing Type) | Applicable (Y/N or N/A) | Comments |
|:--------------------|:------------------------|:---------|
| **Functional Testing** | Y | Core functional testing of NAD reference live update workflow including feature gate behavior, migration triggering, connectivity verification, and spec synchronization |
| **Automation Testing** | Y | All test scenarios will be automated using Ginkgo v2 (tier 1) and pytest (tier 2). Upstream e2e tests in PR #16412 provide a foundation. |
| **Performance Testing** | N/A | Migration performance is covered by existing migration performance tests. No new performance-sensitive code paths introduced. |
| **Security Testing** | N/A | No new RBAC roles, no new API endpoints, no new security boundaries. Existing VM RBAC controls apply. |
| **Usability Testing** | N/A | Feature is API-driven (kubectl patch). No UI changes required for this feature. |
| **Compatibility Testing** | Y | Test with and without Multus Dynamic Networks Controller (DNC) installed. Verify coexistence with existing NIC hotplug/unplug operations. |
| **Regression Testing** | Y | Verify that existing network hotplug, live migration, and VM rollout features are not affected by the new code paths. |
| **Upgrade Testing** | Y | Verify behavior when upgrading from a version without LiveUpdateNADRef to one with it. Verify VMs created before the feature gate existed behave correctly. |
| **Backward Compatibility Testing** | Y | Verify that disabling the feature gate restores previous behavior (NAD changes require restart). Verify no regression in existing RestartRequired logic. |

##### **B. Potential Areas to Consider**

| Item | Description | Applicable (Y/N or N/A) | Comment |
|:-----|:------------|:------------------------|:--------|
| **Dependencies** | Dependent on deliverables from other components/products? Identify what is tested by which team. | Y | Depends on Multus CNI for NAD management, OVS/Linux bridge for network plumbing, KubeVirt migration infrastructure. DNC compatibility must be verified but DNC changes are not required. |
| **Monitoring** | Does the feature require metrics and/or alerts? | N | No new metrics or alerts introduced. Existing migration metrics apply. |
| **Cross Integrations** | Does the feature affect other features/require testing by other components? | Y | Interacts with: (1) NIC hotplug/unplug (shared VM controller code paths), (2) Live migration (triggers migration), (3) VM rollout strategy (LiveUpdate), (4) Workload update controller. Changes to migration Evaluator affect all migration evaluation. |
| **UI** | Does the feature require UI? If so, ensure the UI aligns with the requirements. | N | No UI changes. Feature is API-only (kubectl/oc patch). Future UI integration may be considered but is not in scope for this release. |

#### **5. Test Environment**

| Environment Component | Configuration | Specification Examples |
|:----------------------|:--------------|:-----------------------|
| **Cluster Topology** | Multi-node cluster with at least 2 schedulable worker nodes | 3-node cluster (1 control plane + 2 workers) or 5-node cluster |
| **OCP & OpenShift Virtualization Version(s)** | OCP 4.18+ with CNV v4.22.0+ | OCP 4.18, CNV 4.22.0 |
| **CPU Virtualization** | Standard virtualization-enabled nodes | Intel VT-x or AMD-V enabled |
| **Compute Resources** | Sufficient resources for live migration (source + target VM memory) | 16 GB RAM per worker node minimum |
| **Special Hardware** | None required | N/A |
| **Storage** | Shared storage for live migration (RWX PVCs or LiveMigrate-compatible storage) | OCS/ODF, NFS, or iSCSI with RWX support |
| **Network** | Multiple bridge-based NetworkAttachmentDefinitions on each worker node; Linux bridge or OVS bridge CNI | Two bridge NADs with different VLANs (e.g., VLAN 10 and VLAN 20) or different bridge names (br-1, br-2) |
| **Required Operators** | OpenShift Virtualization operator, Multus CNI (default in OCP) | HyperConverged CR, nmstate operator (optional, for bridge config) |
| **Platform** | Bare metal or nested virtualization (with migration support) | Bare metal preferred; nested virt requires migration support |
| **Special Configurations** | KubeVirt configured with: WorkloadUpdateMethods=LiveMigrate, VMRolloutStrategy=LiveUpdate, FeatureGate=LiveUpdateNADRef | HyperConverged CR with LiveMigrate workload update strategy |

#### **5.5. Testing Tools & Frameworks**

| Category | Tools/Frameworks |
|:---------|:-----------------|
| **Test Framework** | Ginkgo v2 + Gomega (Tier 1 / Go), pytest (Tier 2 / Python) |
| **CI/CD** | OpenShift CI (Prow), Polarion for test case tracking |
| **Other Tools** | kubectl/oc CLI for VM patching, virtctl for VM management, tcpdump/ping for connectivity verification |

#### **6. Entry Criteria**

The following conditions must be met before testing can begin:

- PR [kubevirt/kubevirt#16412](https://github.com/kubevirt/kubevirt/pull/16412) is merged and included in the target build
- LiveUpdateNADRef feature gate is registered and available in KubeVirt configuration
- Test cluster has at least 2 schedulable worker nodes with live migration capability
- At least 2 bridge-based NetworkAttachmentDefinitions are deployed and functional on all worker nodes
- KubeVirt is configured with LiveMigrate workload update strategy and LiveUpdate VM rollout strategy
- Shared storage is available for live migration support
- QE kickoff meeting has been conducted with the development team

#### **7. Risks and Limitations**

| Risk Category | Specific Risk for This Feature | Mitigation Strategy | Status |
|:--------------|:-------------------------------|:--------------------|:-------|
| Timeline/Schedule | PR #16412 is still open and under active review; merge timeline may affect test development | Begin test development using upstream e2e tests as reference; use feature branch for early testing | [ ] |
| Test Coverage | DNC (Dynamic Networks Controller) interaction is complex and may not be fully testable in all CI environments | Document DNC-specific scenarios separately; coordinate with DNC maintainers for integration testing | [ ] |
| Test Environment | Requires multi-node cluster with specific network infrastructure (multiple bridges/VLANs) | Use CI environments with pre-configured network topologies; document setup requirements clearly | [ ] |
| Untestable Aspects | In-place NAD swapping (Option 2 in VEP) is not implemented; cannot test DNC-based swap | Document as known limitation; track as future enhancement if DNC support is added | [ ] |
| Resource Constraints | Live migration requires sufficient cluster resources (memory, CPU) for concurrent VMs | Ensure test environments have adequate resources; use lightweight VM images (Alpine) | [ ] |
| Dependencies | Feature depends on Multus CNI, bridge CNI plugin, and live migration infrastructure | Validate prerequisites in test setup; skip tests gracefully if prerequisites are not met | [ ] |
| Other | Namespace-qualified NAD name handling was flagged in code review as potentially inconsistent | Add explicit test scenarios for namespace-qualified NAD names | [ ] |

#### **8. Known Limitations**

- The feature only supports bridge binding type. Other binding types (SR-IOV, macvtap, passt) are not supported for NAD reference live update.
- Non-migratable VMs cannot use this feature. The NAD reference change requires a live migration to take effect.
- There is a brief network connectivity interruption during the live migration. Seamless connectivity is explicitly not a goal.
- The guest's network configuration (IP address, routes) is not automatically updated after the NAD swap. The VM owner must handle guest-side reconfiguration.
- In-place NAD swapping (without migration) is not supported, even on clusters with Dynamic Networks Controller installed. The current design explicitly avoids patching the source pod's multus annotation to prevent conflicts with DNC.
- The feature does not limit migration retries due to a missing NAD. If the target NAD does not exist, migrations will fail repeatedly.

---

### **III. Test Scenarios & Traceability**

This section provides a **high-level overview** of test scenarios mapped to requirements.

#### **1. Requirements-to-Tests Mapping**

| Requirement ID | Requirement Summary | Test Scenario(s) | Test Type(s) | Priority |
|:---------------|:--------------------|:-----------------|:-------------|:---------|
| REQ-NAD-001 | NAD reference can be changed on a running VM via VM spec patch | TS-001: Verify NAD reference change triggers automatic live migration and VM connects to new network | Tier 1 (Functional), Tier 2 (E2E) | P1 |
| REQ-NAD-002 | VM has connectivity on the new NAD after migration completes | TS-002: Verify post-migration connectivity on new NAD (ping test) and loss of connectivity on old NAD | Tier 1 (Functional), Tier 2 (E2E) | P1 |
| REQ-NAD-003 | LiveUpdateNADRef feature gate controls feature availability | TS-003: Verify NAD reference change does NOT trigger migration when feature gate is disabled | Tier 1 (Functional), Tier 2 (E2E) | P1 |
| REQ-NAD-004 | VMI spec is updated with new NAD reference when feature gate is enabled | TS-004: Verify VMI spec networks[].multus.networkName is updated after VM spec patch | Tier 1 (Functional) | P1 |
| REQ-NAD-005 | VMI spec is NOT updated when feature gate is disabled | TS-005: Verify VMI spec remains unchanged when feature gate is disabled and NAD reference is changed on VM | Tier 1 (Functional) | P1 |
| REQ-NAD-006 | RestartRequired condition is not set for NAD-only changes (feature gate enabled) | TS-006: Verify that changing only the NAD reference does not add RestartRequired condition when feature gate is enabled | Tier 1 (Functional) | P1 |
| REQ-NAD-007 | RestartRequired condition IS set for NAD changes when feature gate is disabled | TS-007: Verify that changing NAD reference sets RestartRequired condition when feature gate is disabled | Tier 1 (Functional) | P2 |
| REQ-NAD-008 | Non-existent NAD reference causes migration failure | TS-008: Verify migration fails when NAD reference is changed to a non-existent NAD; verify VMI spec is still updated | Tier 1 (Functional), Tier 2 (E2E) | P1 |
| REQ-NAD-009 | Guest interface properties (MAC address) are preserved across NAD swap | TS-009: Verify MAC address and interface name inside the guest are unchanged after NAD reference swap and migration | Tier 2 (E2E) | P1 |
| REQ-NAD-010 | Multiple sequential NAD reference changes work correctly | TS-010: Change NAD reference multiple times in sequence; verify each change triggers migration and results in correct connectivity | Tier 2 (E2E) | P2 |
| REQ-NAD-011 | Feature works with namespace-qualified NAD names | TS-011: Use namespace-qualified NAD reference (e.g., `default/nad-name`) and verify migration triggers correctly | Tier 1 (Functional) | P2 |
| REQ-NAD-012 | Feature only applies to bridge binding type | TS-012: Verify that changing NAD reference on a non-bridge binding interface does not trigger migration via this code path | Tier 1 (Functional) | P2 |
| REQ-NAD-013 | Changing non-NAD network properties still requires restart | TS-013: Verify that changing the network name (not networkName) or other network properties still triggers RestartRequired | Tier 1 (Functional) | P2 |
| REQ-NAD-014 | Coexistence with NIC hotplug/unplug operations | TS-014: Perform NAD reference change concurrently with or after NIC hotplug; verify both operations complete correctly | Tier 2 (E2E) | P2 |
| REQ-NAD-015 | VM workload update strategy must be LiveMigrate | TS-015: Verify that NAD reference change behavior depends on WorkloadUpdateMethods including LiveMigrate | Tier 1 (Functional) | P2 |
| REQ-NAD-016 | DNC compatibility - source pod annotation not patched | TS-016: On a cluster with DNC, verify that changing NAD reference does not modify the source pod's multus network annotation; migration is used instead | Tier 2 (E2E) | P2 |
| REQ-NAD-017 | Feature gate registration at Beta level | TS-017: Verify LiveUpdateNADRef feature gate is registered and defaults to enabled at Beta maturity level | Tier 1 (Functional) | P2 |
| REQ-NAD-018 | Upgrade path - VMs created before feature gate exists | TS-018: Verify that VMs created before the LiveUpdateNADRef feature gate was available function correctly after upgrade (no unexpected migrations) | Tier 2 (E2E) | P2 |
| REQ-NAD-019 | Migration condition evaluation includes NAD comparison | TS-019: Verify that the migration evaluator correctly compares NAD names between VMI spec and pod annotation to determine if migration is required | Tier 1 (Functional) | P1 |
| REQ-NAD-020 | VM with interface in Absent state is skipped | TS-020: Verify that interfaces in Absent state are excluded from NAD reference comparison in migration evaluator | Tier 1 (Functional) | P2 |

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - TBD / @tbd
  - TBD / @tbd
- **Approvers:**
  - TBD / @tbd
  - TBD / @tbd
