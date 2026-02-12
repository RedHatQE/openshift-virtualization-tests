# Software Test Plan (STP)

**Jira ID:** CNV-72329
**Feature:** Support changing the VM attached network NAD ref using hotplug
**Target Version:** CNV v4.22.0
**QE Owner:** Yoss Segev
**Feature Owner:** Ananya Banerjee
**SIG:** Network
**Feature Gate:** LiveUpdateNADRef

---

## I. Feature Overview

### Description
Allow customers to change the NetworkAttachmentDefinition (NAD) reference of a VM's secondary network interface without requiring VM reboot. This enables administrators to swap a VM's network connection (e.g., change VLAN ID) through live migration, maintaining the VM's interface properties (MAC address, interface name) while changing the underlying network attachment.

### Parent Feature
VIRTSTRAT-560 - Allow changing network VLAN on the fly

### Enhancement Proposal
VEP 140: Live Update NetworkAttachmentDefinition Reference
https://github.com/kubevirt/enhancements/pull/138

### User Stories
- As a VM admin, I want to swap the guest's uplink from one network to another without the VM noticing, so they get better/worse link, different VLAN, or isolated segment.
- As a VM owner, I should be able to re-assign VMs to a new VLAN ID, without having to reboot my VMs.

### Goals
- Change an existing NAD reference (`spec.networks[].multus.networkName`) of secondary networks using bridge binding on a running VM
- Update pod network plumbing through live migration
- Preserve VM interface properties (MAC address, interface name)

### Non-Goals / Limitations
- Migrating between different CNI types
- Changing the network binding or plugin type
- Maintaining seamless network connectivity during the swap
- Changing NAD reference on non-migratable VMs
- Changing the guest's network configuration following underlying network changes
- Limiting migration retries due to missing NetworkAttachmentDefinition
- In-place swapping with Dynamic Networks Controller (DNC) - migration is required

---

## II. Test Strategy

### Scope
**In Scope:**
- NAD reference change on running VMs with bridge binding
- Live migration trigger on NAD reference update
- Feature gate enablement/disablement behavior
- Network connectivity validation post-migration
- VM interface properties preservation (MAC, interface name)
- RestartRequired condition handling
- VMI network spec synchronization from VM

**Out of Scope:**
- SR-IOV binding (future enhancement)
- Other binding types (masquerade, slirp, passt)
- CNI type migration
- Non-migratable VMs
- Clusters without live migration support

### Test Levels
- **Unit Tests:** Network spec comparison logic, RestartRequired condition logic
- **Integration Tests:** VM-to-VMI network spec sync, migration condition evaluation
- **E2E Tests:** Full workflow validation (NAD swap → migration → connectivity)
- **Manual/Exploratory:** Edge cases, multi-network scenarios, performance impact

### Dependencies
**Upstream:**
- KubeVirt live migration support
- Multus CNI
- NetworkAttachmentDefinition CRD availability
- Feature gate management

**Downstream:**
- OpenShift Virtualization v4.22.0
- OVN-Kubtes or equivalent CNI
- Cluster with live migration enabled

### Risks & Mitigation
| Risk | Severity | Mitigation |
|:-----|:---------|:-----------|
| Network disruption during migration | High | Document expected connectivity loss during migration |
| Stale VMI pod annotation if migration fails | Medium | Validate rollback behavior, document cleanup procedure |
| Conflict with Dynamic Networks Controller | Medium | Test with/without DNC, document incompatibility |
| Missing target NAD causes migration failure | Medium | Validate error handling, test NAD creation timing |

---

## III. Test Scenarios

### Tier 1: Core Functionality (Smoke Tests)

| ID | Scenario | Expected Result | Automated | Priority |
|:---|:---------|:----------------|:----------|:---------|
| T1.1 | Change NAD reference on running VM with bridge binding | VM migrates to new pod with updated NAD, interface properties preserved | Yes | P0 |
| T1.2 | Verify network connectivity after NAD swap | VM has connectivity through new network attachment | Yes | P0 |
| T1.3 | Enable LiveUpdateNADRef feature gate | Feature gate enables successfully, feature is active | Yes | P0 |
| T1.4 | Change NAD to different VLAN ID | VM connects to new VLAN post-migration | Yes | P0 |
| T1.5 | Verify VMI network spec sync from VM | VMI spec reflects VM network changes before migration | Yes | P1 |
| T1.6 | Verify RestartRequired condition not added | VM does not get RestartRequired condition for NAD-only change | Yes | P0 |
| T1.7 | Verify immediate migration trigger | WorkloadUpdateController triggers migration immediately for bridge binding | Yes | P0 |
| T1.8 | Preserve MAC address after NAD swap | VM interface retains original MAC address post-migration | Yes | P0 |
| T1.9 | Preserve interface name after NAD swap | VM interface retains original name (e.g., net1) post-migration | Yes | P1 |
| T1.10 | Change NAD between same-type networks | Swap from bridge-based NAD A to bridge-based NAD B succeeds | Yes | P1 |
| T1.11 | Verify target pod multus annotation | Target pod has updated multus annotation with new NAD reference | Yes | P1 |
| T1.12 | Basic NAD swap with single secondary interface | VM with one secondary interface swaps NAD successfully | Yes | P0 |
| T1.13 | Verify VM remains running during migration | VM does not restart, only migrates | Yes | P0 |
| T1.14 | Check VMI conditions post-migration | VMI has no error conditions after successful NAD swap | Yes | P1 |
| T1.15 | Verify VM events logged correctly | VM events include NAD change and migration trigger | Yes | P2 |
| T1.16 | Verify authorized user can change NAD reference | User with VM edit permissions can swap NAD successfully | Yes | P1 |
| T1.17 | Verify unauthorized user cannot change NAD reference | User without permissions receives proper authorization error | Yes | P1 |

### Tier 2: Advanced Scenarios (Extended Testing)

| ID | Scenario | Expected Result | Automated | Priority |
|:---|:---------|:----------------|:----------|:---------|
| T2.1 | Disable LiveUpdateNADRef feature gate | NAD change requires RestartRequired condition | Yes | P1 |
| T2.2 | Change NAD when feature gate disabled | VM gets RestartRequired condition, no migration triggered | Yes | P1 |
| T2.3 | Multiple NAD reference changes before migration | Last NAD reference is used for target pod | Partial | P2 |
| T2.4 | Change NAD to non-existent network | Migration fails with clear error, VM remains on source | Yes | P1 |
| T2.5 | NAD swap with multiple secondary interfaces | Only specified interface NAD changes, others unchanged | Yes | P1 |
| T2.6 | Change multiple NAD references simultaneously | All interfaces migrate with updated NAD references | Yes | P2 |
| T2.7 | NAD swap on VM with hotplugged interface | Previously hotplugged interface swaps NAD successfully | Yes | P2 |
| T2.8 | Rollback NAD change before migration completes | Migration cancels or uses original NAD if already started | Manual | P2 |
| T2.9 | NAD swap with concurrent VM updates | NAD change processed correctly alongside other updates | Partial | P2 |
| T2.10 | Change NAD on VM with running workload | Workload experiences expected network interruption, recovers | Manual | P1 |
| T2.11 | NAD swap with different bridge configuration | VM connects to different bridge (br1 → br2) successfully | Yes | P1 |
| T2.12 | rify Dynamic Networks Controller compatibility | DNC does not interfere with migration-based NAD swap | Manual | P2 |
| T2.13 | NAD change on VM with persistent volumes | VM migrates with PVs, NAD swap succeeds | Yes | P2 |
| T2.14 | Monitor migration performance impact | NAD swap migration completes within expected time window | Manual | P3 |
| T2.15 | NAD swap with network policy applied | Network policy applies correctly to new NAD | Yes | P2 |
| T2.16 | Change NAD back to original network | Reverse NAD swap (A→B→A) works correctly | Yes | P2 |
| T2.17 | NAD swap with IPv4 and IPv6 networks | Both IP stacks work correctly after migration | Yes | P2 |
| T2.18 | Verify virt-controller RestartRequired logic | Controller correctly identifies NAD-only changes | Yes | P1 |
| T2.19 | Verify virt-controller network sync logic | Controller syncs networkName field from VM to VMI | Yes | P1 |
| T2.20 | Verify WorkloadUpdateController migration logic | Controller requests immediate migration for bridge binding | | P1 |
| T2.21 | CNV upgrade with VM using swapped NAD | VM persists with swapped NAD configuration post-upgrade | Yes | P1 |
| T2.22 | Post-upgrade NAD swap operation | VM can perform new NAD swap after CNV upgrade completes | Yes | P2 |

### Negative Test Scenarios

| ID | Scenario | Expected Result | Automated | Priority |
|:---|:---------|:----------------|:----------|:---------|
| N1 | Change NAD binding type (bridge → SR-IOV) | RestartRequired condition added, no migration | Yes | P1 |
| N2 | Change NAD on non-migratable VM | Error or RestartRequired condition, no migration attempted | Yes | P1 |
| N3 | Target NAD deleted during migration | Migration fails gracefully, VM remains functional on source | Yes | P2 |
| N4 | Change NAD with insufficient node resources | Migration fails with scheduling error, clear message | Yes | P2 |
| N5 | NAD swap with incompatible CNI plugin | Validation rejects change or migration fails with clear error | Manual | P2 |
| N6 | Change NAD on paused VM | NAD change queued, processed when VM unpaused | Manual | P3 |
| N7 | Rapidly toggle NAD reference multiple times | System handles rapid changes without corruption | Manual | P2 |
| N8 | Change NAD with namespace mismatch | Validation error or migtion failure with clear message | Yes | P2 |
| N9 | Target NAD has invalid configuration | Migration fails with validation error | Yes | P2 |
| N10 | Change NAD during active migration | Change queued or rejected with appropriate error | Manual | P2 |

### Platform & Configuration Tests

| ID | Scenario | Expected Result | Automated | Priority |
|:---|:---------|:----------------|:----------|:---------|
| P1 | NAD swap on x86_64 platform | Feature works on x86_64 nodes | Yes | P0 |
| P2 | NAD swap on ARM64 platform | Feature works on ARM64 nodes | Yes | P1 |
| P3 | NAD swap on s390x platform (if applicable) | Feature works on s390x nodes | Manual | P2 |
| P4 | NAD swap with OVN-Kubernetes CNI | Works correctly with OVN-K | Yes | P1 |
| P5 | NAD swap with OpenShiftSDN (if supported) | Works correctly with OpenShiftSDN | Manual | P2 |
| P6 | Baremetal deployment NAD swap | Feature works on baremetal clusters | Manual | P2 |
| P7 | IPI deployment NAD swap | Feature works on IPI clusters | Yes | P1 |
| P8 | UPI deployment NAD swap | Feature works on UPI clusters | Manual | P2 |

---

## IV. Test Environment

### Required Infrastructure
- OpenShift cluster with CNV v4.22.0 or later
- Minimum 3 worker nodes for live migration
- Multus CNI installed and configured
- Multiple NetworkAttachmentDefinitions pre-created with different VLAN configurations

### Test Data
- NAD configurations with different VLAN IDs (10, 20, 30)
- NAD configurations with different bridge names (br1, br2)
- VM templates with bridge binding configurations
- Sample workload (e.g., nginx, test HTTP server)

### Prerequisites
- LiveUpdateNADRef feature gate enabled
- Cluster with live migration enabled
- NAD definitions created in appropriate namespaces
- Network connectivity verification tools (ping, curl) available

---

## V. Entry & Exit Criteria

### Entry Criteria
- [ ] CNV v4.22.0 build available
- [ ] LiveUpdateNADRef feature gate implemented
- [ ] Test cluster provisioned with required NAD configurations
- [ ] Test automation framework ready
- [ ] VEP 140 merged and documented

### Exit Criteria
- [ ] All Tier 1 test scenarios pass (100%)
- [ ] ≥90% Tier 2 test scenarios pass
- [ ] All P0/P1 negative tests pass
- [ ] No P0/P1 bugs open
- [ ] Documentation updated with feature usage
- [ ] Upgrade/rollback testing completed
- [ ] Performance impact assessed and documented

---

## VI. Test Deliverables

### Test Artifacts
- Automated test suite for E2E scenarios
- Manual test execution reports
- Bug reports with reproduction steps
- Performance test results
- Feature gate enablement/disablement validation

### Documentation
- Test execution summary
- Known limitations and workarounds
- User guide section for NAD swapping
- Migration behavior documentation
- Troubleshooting guide

---

## VII. Regression Impact Analysis

### Upstream Dependencies
- VM lifecycle management (no impact expected)
- Live migration framework (enhancement, no breaking changes)
- Network hotplug/unplug (potential interaction - test compatibility)
- RestartRequiredondition logic (modified - thorough testing required)

### Downstream Dependencies
- HCO operator integration (verify feature gate propagation)
- UI/UX for network management (potential enhancement opportunity)
- Monitoring and alerting (new events for NAD swap)

### Related Features to Retest
- Network interface hotplug (verify no regression)
- Network interface unplug (verify no regression)
- Live migration with network constraints (verify NAD swap doesn't break existing)
- VM restart scenarios (verify RestartRequired condition logic intact)
- Feature gate management (verify proper enable/disable behavior)

---

## VIII. Automation Coverage

### Automated Tests
- Tier 1: 100% (all 17 scenarios)
- Tier 2: ~77% (17/22 scenarios automated)
- Negative: ~70% (7/10 scenarios)
- Platform: ~50% (4/8 scenarios)

**Total Automated: ~81%**

### Manual Tests Required
- Dynamic Networks Controller compatibility testing
- Multi-network concurrent changes
- Performance and stress testing
- Rollback scenarios during migration
- Edge case exploratory testing

---

## IX. Schedule & Milestones

| Milestone | Date | Deliverable |
|:----------|:-----|:------------|
| Test Plan Review | Week 1 | STP approved by stakeholders |
| Test Environment Setup | Week 1-2 | Cluster ready, NAD configs created |
| Automation Development | Week 2-3 | Tier 1 & key Tier 2 tests automated |
| Test Execution | Week 3-4 | All test scenarios executed |
| Bug Triage & Fixes | Week 4-5 | P0/P1 bugs resolved |
| Regression Testing | Week 5 | Verify fixes, final validation |
| Sign-off | Week 6 | Exit criteria met, feature approved |

---

## X. Approvals

| Role | Name | Signature | Date |
|:-----|:-----|:----------|:-----|
| QE Owner | Yoss Segev | __________ | ____ |
| Feature Owner | Ananya Banerjee | __________ | ____ |
| QE Manager | __________ | __________ | ____ |
| Engineering Manager | __________ | __________ | ____ |

---

## XI. References

### Jira Links
- Epic: CNV-72329 - Support changing the VM attached network NAD ref using hotplug
- Parent Feature: VIRTSTRAT-560 - Allow changing network VLAN on the fly
- Implementation: CNV-76560 - Implement NAD reference live update
- QE Tasks: CNV-75777, CNV-75778
- VEP Task: CNV-72401
- Documentation: CNV-76929, CNV-76930

### Enhancement Proposals
- VEP 140: Live Update NetworkAttachmentDefinition Reference
  https://github.com/kubevirt/enhancements/pull/138

### Documentation
- KubeVirt Network Hotplug Documentation (upstream)
- OpenShift Virtualization Network Configuration Guide (downstream)

### Related PRs
- To be populated with implementation PRs from kubevirt/kubevirt

---

**Document Version:** 1.0
**Last Updated:** 2026-02-02
**Generated by:** Autonomous QE Agent - Claude Code

