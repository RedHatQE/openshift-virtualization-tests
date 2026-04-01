"""
Storage migration cleanup tests for MultiNamespaceVirtualMachineStorageMigrationPlan.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Namespace level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Spec level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Combination of namespace and spec level for MultiNamespaceVirtualMachineStorageMigrationPlan

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md
"""

import pytest

__test__ = False


class TestStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for MultiNamespaceVirtualMachineStorageMigrationPlan.

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_retention_policy_default_behavior(self):
        """
        Test that default behavior is keepSource when retentionPolicy is not specified in MultiNamespaceVirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan without retentionPolicy field
               (neither spec-level nor namespace-level)
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume

        Steps:
            1. Verify source PVC/DataVolume still exists (default behavior)

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (default keepSource behavior)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_namespace_level_retention_policy_delete_source(self):
        """
        Test namespace-level retentionPolicy=deleteSource in MultiNamespaceVirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with namespace-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume is deleted
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_spec_level_retention_policy_delete_source(self):
        """
        Test spec-level retentionPolicy=deleteSource in MultiNamespaceVirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with spec-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume is deleted
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted (spec-level policy)
            - VM is running on new storage
        """

class TestStorageMigrationCombinedRetentionPolicy:
    """
    Test combination of retentionPolicy for MultiNamespaceVirtualMachineStorageMigrationPlan.

    Preconditions:
      1. Two VMs with source PVCs/DataVolumes
      2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
        - spec-level retentionPolicy=keepSource
        - namespace-level retentionPolicy=deleteSource for specific namespace
      3. Wait for all migrations to complete successfully
      4. Verify the two VMs are using new PVCs

    """
    @pytest.mark.polarion("CNV-XXXXX")
    def test_combined_namespace_and_spec_level_retention_policy(self):
        """
        Test combination of namespace-level and spec-level retentionPolicy.
        Namespace-level policy should override spec-level policy for that namespace.

        Steps:
            1. Verify source PVCs in namespaces WITHOUT namespace-level policy are kept (spec-level policy)
            2. Verify source PVCs in namespaces WITH namespace-level policy=deleteSource are deleted

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are deleted
            - Source PVCs in other namespaces are kept (spec-level policy)
        """
