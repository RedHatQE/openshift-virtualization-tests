"""
Storage migration cleanup tests for storage migration plans.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Namespace level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Plan level (spec) for MultiNamespaceVirtualMachineStorageMigrationPlan
- Combination of namespace and plan level for MultiNamespaceVirtualMachineStorageMigrationPlan
  (namespace-level overrides plan-level when both are configured)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md
"""
