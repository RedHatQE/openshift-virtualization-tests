# Ticket Assessment: CNV-79308

## Classification

- **Ticket type:** Epic
- **Feature:** Clone and Storage Migration support for VMState PVC
- **Risk level:** High — persistent TPM, EFI, or CBT state must remain usable across clone and migration workflows.
- **Evidence quality:** High for design and implementation scope; medium for downstream release commitments because implementation remains open.

## Testable Requirements

1. **AC-1:** VM clones work with VMState PVC.
2. **AC-2:** Storage migration of VMState PVC is supported.
3. **Design constraint:** Declarative state supports generated storage, adopted storage, or both, with observable ownership and lifecycle behavior.
4. **Compatibility constraint:** Existing implicit VM state behavior remains supported.

## Evidence and Gaps

- Merged VEP 312 defines clone, migration, adoption, ownership, cleanup, validation, and compatibility behavior.
- Open PR 16634 implements clone support; draft PR 19173 implements the broader declarative VM state design.
- Existing downstream QE coverage validates standard cloning, storage migration, Windows vTPM integrity, rollback, and cleanup, but not the declarative source/template matrix.
- Jira CNV-98256 says PR 19173 is merged, while GitHub reports an open draft on September 29, 2026.
- The KubeVirt Alpha target is v1.10; downstream CNV v5.1.0 maturity and final sign-off ownership still require confirmation.

**Verdict:** READY
