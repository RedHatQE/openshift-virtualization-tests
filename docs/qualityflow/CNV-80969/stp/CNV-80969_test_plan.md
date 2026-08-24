# OpenShift Virtualization (CNV) — Windows VM Disk PCI Address Stability After Upgrade Quality Engineering Plan

**Jira ID:** [CNV-80969](https://issues.redhat.com/browse/CNV-80969)
**Author:** QualityFlow (automated)
**Date:** 2026-08-24
**Product Version:** CNV v4.20.8 (fix), CNV v4.20.7 (affected)
**Priority:** Critical
**Component:** Storage Platform

## Section I: Motivation & Requirements Review

### I.1 — Requirements Checklist

- [x] Acceptance criteria defined in Jira ticket (steps to reproduce, expected vs. actual behavior documented)
- [x] Feature scope is clear and bounded (PCI address reservation behavior during CNV upgrade path)
- [x] Dependencies identified (kubevirt/kubevirt PR #17060 fix merged; root cause PR #14754 identified)

### I.2 — Known Limitations

- **Windows-specific disk management:** Windows marks disks as offline when their PCI address changes; Linux VMs may also be affected if udev rules reference PCI device paths (confirmed in Jira comments by Red Hat support engineers).
- **v2 VMs are not migrated to v3:** By design, VMs that already adopted v2 topology (rebooted on 4.20 before fix) retain v2. Disks manually re-onlined by the user remain online on subsequent reboots but the PCI addresses stay at v2 offsets.
- **Memory threshold edge case:** VMs with <=2GB memory may have ambiguous version detection between v1 and v2, annotated as v3 (documented as harmless in PR #17060).
- **No local source repository available:** LSP-based regression analysis was skipped. Impact analysis is derived from PR diffs and Jira comments only.

### I.3 — Technology & Root Cause Review

**Root cause:** PR [kubevirt/kubevirt#14754](https://github.com/kubevirt/kubevirt/pull/14754) introduced v2 hotplug port reservation that scales PCI placeholder count based on VM memory. On upgrade from 4.19 to 4.20, existing VMs received more placeholders than originally defined, shifting all disk PCI addresses (e.g., from bus 0x07-0x0a to 0x0a-0x0d). Windows treats disks at new PCI addresses as new/offline devices.

**Fix:** PR [kubevirt/kubevirt#17060](https://github.com/kubevirt/kubevirt/pull/17060) introduces v3 PCI topology:
- Uses v1's fixed placeholder count `max(0, 4-interfaces)` for address stability
- Delivers extra hotplug capacity as pcie-root-port controllers appended after device addressing (no PCI address shift)
- Freezes existing v2 VMs' placeholder count via annotation (no migration to v3)
- v1 VMs naturally become v3 on upgrade

**Files changed in fix (PR #17060, ~22 files):**
- `staging/src/kubevirt.io/api/core/v1/types.go` (annotation constants)
- `pkg/virt-launcher/virtwrap/manager.go` (allocateHotplugPorts, v3 formulas)
- `pkg/virt-launcher/virtwrap/network/nichotplug.go` (WithNetworkIfacesResources)
- `pkg/virt-launcher/virtwrap/converter/pci-placement.go` (CountPCIDevices)
- `pkg/virt-api/webhooks/mutating-webhook/mutators/vmi-mutator.go` (VMI webhook)
- `pkg/virt-api/webhooks/mutating-webhook/mutators/vm-mutator.go` (VM webhook)
- `pkg/virt-handler/pci_topology.go` (detection logic)
- `pkg/virt-controller/watch/vm/vm.go` (annotation propagation)
- `docs/pci-topology.md` (new documentation)
- Test files: `pci_topology_test.go`, `tests/hotplug/pci_topology.go`

## Section II: Software Test Plan

### II.1 — Scope

This test plan covers the PCI address stability fix for Windows (and Linux) VM disks across CNV version upgrades. The scope includes:

**In scope:**
- PCI address preservation during 4.19 to 4.20 upgrade path
- PCI topology version annotation correctness (v1, v2, v3)
- Windows VM disk online/offline state after upgrade + reboot
- Multiple upgrade path combinations (running vs. stopped VMs, with/without intermediate broken build)
- Multi-disk VMs (4-5 VirtIO disks)
- Storage class independence
- Memory threshold behavior (<=2GB vs. >2GB)
- Linux VMs with udev rules referencing PCI paths

**Out of scope:**
- Non-VirtIO disk types (IDE, SCSI)
- Network hotplug functionality itself (tested separately)
- s390x architecture-specific PCI slot handling (covered by separate PRs #17269, #17327)

### II.2 — Goals

1. Verify that disk PCI addresses remain stable across the 4.19-to-4.20 upgrade path with the fix applied
2. Verify that all Windows VM disks remain online after upgrade and reboot (no manual intervention required)
3. Verify correct PCI topology version annotation (v2 vs. v3) for different VM lifecycle states
4. Verify that VMs on the broken 4.20.7 build can be upgraded to the fixed 4.20.8 without further disruption
5. Verify that newly created VMs on fixed builds get v3 topology by default

### II.3 — Strategy

**Test approach:** End-to-end functional testing on real OpenShift clusters with CNV operator upgrades.

**Test labels:**
- **e2e** (end-to-end): Full upgrade path scenarios with actual Windows/Linux VMs
- **functional**: Individual PCI topology behaviors (annotation, address calculation)
- **integration**: Interaction between virt-handler, virt-launcher, and virt-controller during upgrades

**Prioritization:** The 6 scenarios documented by QE in the Jira ticket form the P1 core test matrix. Additional scenarios for Linux VMs, edge cases, and negative testing are P2.

### II.4 — Environment Requirements

- **Platform:** Kubernetes (OpenShift)
- **CLI tools:** kubectl, oc
- **CNV versions needed:**
  - CNV v4.19.x (starting version, e.g., v4.19.18 or v4.19.19)
  - CNV v4.20.7 (broken build, without fix)
  - CNV v4.20.8 (fixed build, with fix)
- **OCP version:** 4.19.x (start), 4.20.x (target)
- **Guest OS:** Windows Server 2022 (primary), Linux with udev rules (secondary)
- **VM requirements:** Memory > 2 GiB, 4-5 VirtIO disks
- **Storage:** Any storage class providing block-mode PVs (storage class independent per Jira confirmation)

### II.5 — Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Upgrade path timing sensitivity (VM state at exact upgrade moment) | Medium | High | Test both running and stopped VM states at each upgrade step |
| Storage class-specific behavior | Low | Medium | Confirmed storage-class-independent in Jira; validate with at least 2 storage classes |
| Linux VM impact via udev rules | Medium | High | Include Linux VM scenario with PCI-based udev rules |
| Memory threshold edge case (<=2GB) | Low | Low | Documented as harmless; include one scenario with 2GB VM |
| Test environment availability (multi-version upgrade cluster) | Medium | Medium | Pre-provision clusters with known-good IIB references from QE testing |

## Section III: Test Scenarios & Traceability

### Requirements Mapping

- **[CNV-80969]** — Windows VM disks go offline after rebooting following upgrade to 4.20 due to PCI address shift from v2 hotplug port reservation

  - **REQ-01:** PCI addresses must remain stable for existing VM disks across 4.19 to 4.20 upgrade
  - **REQ-02:** Fix must handle both upgrade scenarios (VM running vs. stopped during upgrade)
  - **REQ-03:** v2 VMs must have placeholder count frozen via annotation (not migrated to v3)
  - **REQ-04:** v1 VMs must naturally become v3 on upgrade
  - **REQ-05:** Correct PCI topology version annotation (v2/v3) must be set per VM lifecycle state
  - **REQ-06:** All Windows VM disks must remain online after upgrade + reboot (no manual intervention)
  - **REQ-07:** Fix must work with multiple disks (4-5 VirtIO disks per VM)
  - **REQ-08:** Linux VMs with PCI-based udev rules must not have device mapping broken
  - **REQ-09:** Behavior must be storage-class-independent
  - **REQ-10:** Newly created VMs on fixed builds must get v3 topology by default

- **[CNV-81215]** — Block 4.19 to 4.20 upgrade (linked: causes)

  - REQ-01, REQ-02 coverage applies (upgrade blocking was a consequence of this bug)

- **[CNV-80574]** — Windows disks offline after upgrading to CNV 4.20, migrated via MTV from 4.18 (duplicate)

  - REQ-01, REQ-06 coverage applies

### Test Scenarios

#### P1 -- Core Upgrade Path Scenarios (e2e)

- **[CNV-80969]** — REQ-01, REQ-02, REQ-05, REQ-06, REQ-07
  - **TS-01: Upgrade 4.19->broken->fixed, VM running at each stage, disks manually re-onlined on broken build** [e2e, P1]
    - Preconditions: Windows Server 2022 VM with 5 VirtIO disks on CNV 4.19, all disks online with simple volumes, memory > 2 GiB
    - Steps:
      1. Upgrade to CNV 4.20.7 (without fix)
      2. Stop and start VM; verify disks go offline (confirms bug reproduction)
      3. Manually re-online disks via Windows Disk Manager
      4. Upgrade to CNV 4.20.8 (with fix)
      5. Verify v2 annotation in VMI
      6. Stop and start VM
    - Expected: v2 annotation present; all disks remain online after final reboot

- **[CNV-80969]** — REQ-01, REQ-02, REQ-03, REQ-05, REQ-06
  - **TS-02: Upgrade 4.19->broken->fixed, VM rebooted on broken build, disks NOT manually re-onlined** [e2e, P1]
    - Preconditions: Same as TS-01
    - Steps:
      1. Upgrade to CNV 4.20.7 (without fix)
      2. Stop and start VM; verify disks go offline
      3. Do NOT manually re-online disks
      4. Upgrade to CNV 4.20.8 (with fix)
      5. Verify v2 annotation in VMI
      6. Stop and start VM
    - Expected: v2 annotation present; disks remain offline (v2 frozen, PCI addresses already shifted; user must manually re-online once)

- **[CNV-80969]** — REQ-01, REQ-02, REQ-04, REQ-05, REQ-06
  - **TS-03: Upgrade 4.19->broken->fixed, VM kept running through both upgrades (never rebooted on broken)** [e2e, P1]
    - Preconditions: Same as TS-01
    - Steps:
      1. Upgrade to CNV 4.20.7 (without fix); do NOT touch VM
      2. Upgrade to CNV 4.20.8 (with fix)
      3. Verify v3 annotation in VMI
      4. Stop and start VM
    - Expected: v3 annotation present; all disks remain online (PCI addresses preserved from 4.19 topology)

- **[CNV-80969]** — REQ-01, REQ-02, REQ-04, REQ-05, REQ-06
  - **TS-04: Upgrade 4.19->broken->fixed, VM stopped before any upgrade** [e2e, P1]
    - Preconditions: Same as TS-01
    - Steps:
      1. Stop VM on CNV 4.19
      2. Upgrade to CNV 4.20.7 (without fix); do NOT touch VM
      3. Upgrade to CNV 4.20.8 (with fix)
      4. Start VM
    - Expected: v3 annotation present; all disks remain online

- **[CNV-80969]** — REQ-01, REQ-05, REQ-06
  - **TS-05: VM created on broken build (4.20.7), upgraded to fixed build (4.20.8), VM running** [e2e, P1]
    - Preconditions: CNV 4.20.7 cluster, no prior VMs
    - Steps:
      1. Create Windows VM with 5 VirtIO disks on CNV 4.20.7
      2. Start VM, online all disks, create simple volumes
      3. Upgrade to CNV 4.20.8 (with fix)
      4. Verify v2 annotation in VMI
      5. Stop and start VM
    - Expected: v2 annotation present; all disks remain online (v2 placeholder count frozen)

- **[CNV-80969]** — REQ-01, REQ-05, REQ-06
  - **TS-06: VM created on broken build (4.20.7), stopped, then upgraded to fixed build (4.20.8)** [e2e, P1]
    - Preconditions: Same as TS-05
    - Steps:
      1. Create Windows VM with 5 VirtIO disks on CNV 4.20.7
      2. Start VM, online all disks, create simple volumes
      3. Stop VM
      4. Upgrade to CNV 4.20.8 (with fix)
      5. Start VM
    - Expected: v3 annotation present; disks may initially be offline (PCI address change from v2 allocation to v3); after manual re-online, subsequent reboots preserve disk state

#### P2 -- Extended Scenarios (functional / e2e)

- **[CNV-80969]** — REQ-10, REQ-05
  - **TS-07: New VM created on fixed build (4.20.8) gets v3 topology by default** [functional, P2]
    - Preconditions: Clean CNV 4.20.8 cluster
    - Steps:
      1. Create new Windows VM with 5 VirtIO disks
      2. Start VM
      3. Inspect VMI annotations
      4. Online all disks
      5. Stop and start VM
    - Expected: v3 annotation set by mutating webhook; all disks online; PCI addresses stable across reboot

- **[CNV-80969]** — REQ-08
  - **TS-08: Linux VM with PCI-based udev rules survives upgrade** [e2e, P2]
    - Preconditions: Linux VM on CNV 4.19 with udev rules mapping PCI device paths to disk names, 4 VirtIO disks
    - Steps:
      1. Configure udev rules referencing PCI bus addresses for disk naming
      2. Upgrade to CNV 4.20.8 (with fix, skipping broken build)
      3. Reboot VM
      4. Verify udev-named devices still map correctly
    - Expected: PCI addresses unchanged; udev rules produce same device names

- **[CNV-80969]** — REQ-09
  - **TS-09: Storage class independence verification** [functional, P2]
    - Preconditions: Windows VM on CNV 4.19, disks on two different storage classes (e.g., OCS Ceph RBD and local storage)
    - Steps:
      1. Create VM with disks on different storage classes
      2. Upgrade to CNV 4.20.8
      3. Reboot VM
    - Expected: All disks online regardless of storage class

- **[CNV-80969]** — REQ-05
  - **TS-10: Memory threshold edge case (VM with exactly 2GB memory)** [functional, P2]
    - Preconditions: Windows VM with memory = 2 GiB on CNV 4.19
    - Steps:
      1. Create VM with exactly 2 GiB memory and 3 VirtIO disks
      2. Upgrade to CNV 4.20.8
      3. Inspect annotation (may show v3 due to ambiguous detection)
      4. Reboot VM
    - Expected: VM operates correctly; annotation is v3; disks remain online

- **[CNV-80969]** — REQ-05, REQ-03
  - **TS-11: Annotation persistence across live migration** [integration, P2]
    - Preconditions: Multi-node cluster, Windows VM on CNV 4.20.8 with v3 annotation
    - Steps:
      1. Trigger live migration of VM to another node
      2. Verify annotation preserved on target node
      3. Stop and start VM
    - Expected: PCI topology annotation survives migration; disks remain at stable addresses

- **[CNV-80969]** — REQ-01
  - **TS-12: Direct 4.19 to fixed 4.20.8 upgrade (no broken build in path)** [e2e, P2]
    - Preconditions: Windows VM with 5 VirtIO disks on CNV 4.19, all online
    - Steps:
      1. Upgrade directly from CNV 4.19 to CNV 4.20.8 (with fix)
      2. Reboot VM
    - Expected: v3 annotation; all disks online; PCI addresses unchanged

### Test Counts Summary

| Label | P1 | P2 | Total |
|-------|----|----|-------|
| e2e | 6 | 3 | 9 |
| functional | 0 | 3 | 3 |
| integration | 0 | 1 | 1 |
| **Total** | **6** | **6** | **12** |

## Section IV: Sign-off & Approval

| Role | Name | Date | Verdict |
|------|------|------|---------|
| QE Lead | | | |
| Dev Lead | | | |
