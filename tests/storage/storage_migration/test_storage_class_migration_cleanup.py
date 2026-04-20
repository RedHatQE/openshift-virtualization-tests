"""
Storage migration cleanup tests for storage migration plans.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Spec level for VirtualMachineStorageMigrationPlan (single namespace)
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

    @pytest.mark.polarion("CNV-XXXXX")
    def test_namespace_level_retention_policy_keep_source(self):
        """
        Test namespace-level retentionPolicy=keepSource in MultiNamespaceVirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with namespace-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume still exists
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (namespace-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_spec_level_retention_policy_keep_source(self):
        """
        Test spec-level retentionPolicy=keepSource in MultiNamespaceVirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with spec-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume still exists
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (spec-level policy)
            - VM is running on new storage
        """


class TestSingleNamespaceStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for VirtualMachineStorageMigrationPlan (single namespace).

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_single_namespace_retention_policy_keep_source(self):
        """
        Test spec-level retentionPolicy=keepSource in VirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with spec-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume still exists
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (spec-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_single_namespace_retention_policy_delete_source(self):
        """
        Test spec-level retentionPolicy=deleteSource in VirtualMachineStorageMigrationPlan.
        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with spec-level retentionPolicy=deleteSource
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

    @pytest.mark.polarion("CNV-XXXXX")
    def test_combined_namespace_keep_spec_delete(self):
        """
        Test combination: namespace-level keepSource + spec-level deleteSource.
        Spec-level policy should override namespace-level policy.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - spec-level retentionPolicy=deleteSource
                - namespace-level retentionPolicy=keepSource for specific namespace
            3. Wait for all migrations to complete successfully
            4. Verify the two VMs are using new PVCs

        Steps:
            1. Verify source PVCs in namespaces WITHOUT namespace-level policy are deleted (spec-level policy)
            2. Verify source PVCs in namespaces WITH namespace-level policy=keepSource are kept

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are kept
            - Source PVCs in other namespaces are deleted (spec-level policy)
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_combined_both_delete(self):
        """
        Test combination: namespace-level deleteSource + spec-level deleteSource.
        Both policies agree on deletion.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - spec-level retentionPolicy=deleteSource
                - namespace-level retentionPolicy=deleteSource for specific namespace
            3. Wait for all migrations to complete successfully
            4. Verify the two VMs are using new PVCs

        Steps:
            1. Verify all source PVCs are deleted (both policies agree)

        Expected:
            - All migrations complete successfully
            - All source PVCs are deleted
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_combined_both_keep(self):
        """
        Test combination: namespace-level keepSource + spec-level keepSource.
        Both policies agree on retention.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - spec-level retentionPolicy=keepSource
                - namespace-level retentionPolicy=keepSource for specific namespace
            3. Wait for all migrations to complete successfully
            4. Verify the two VMs are using new PVCs

        Steps:
            1. Verify all source PVCs are kept (both policies agree)

        Expected:
            - All migrations complete successfully
            - All source PVCs are kept
        """


class TestStorageMigrationFailureRetentionPolicy:
    """
    Test retentionPolicy behavior when migration fails.
    Source volumes should be retained regardless of retentionPolicy setting.

    Preconditions:
      - VM with source PVC/DataVolume
      - Configuration that causes migration to fail
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_failed_migration_with_delete_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=deleteSource.

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with spec-level retentionPolicy=deleteSource
            2. Configure migration to fail (e.g., invalid target storage class, insufficient quota)
            3. Wait for migration to fail

        Steps:
            1. Verify migration failed
            2. Verify source PVC/DataVolume still exists (not deleted despite deleteSource policy)
            3. Verify VM is still using original PVC/DataVolume

        Expected:
            - Migration fails as expected
            - Source PVC/DataVolume is retained (safety mechanism)
            - VM continues running on original storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_failed_migration_with_keep_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=keepSource.

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with spec-level retentionPolicy=keepSource
            2. Configure migration to fail (e.g., invalid target storage class, insufficient quota)
            3. Wait for migration to fail

        Steps:
            1. Verify migration failed
            2. Verify source PVC/DataVolume still exists
            3. Verify VM is still using original PVC/DataVolume

        Expected:
            - Migration fails as expected
            - Source PVC/DataVolume is retained (as per policy)
            - VM continues running on original storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_failed_multi_namespace_migration_with_delete_source_policy(self):
        """
        Test that source PVCs are retained when MultiNamespace migration fails with retentionPolicy=deleteSource.

        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - spec-level retentionPolicy=deleteSource
                - namespace-level retentionPolicy=deleteSource for specific namespace
            2. Configure migration to fail for at least one VM
            3. Wait for migration to fail

        Steps:
            1. Verify migration failed
            2. Verify all source PVCs/DataVolumes still exist (not deleted despite deleteSource policy)
            3. Verify VMs are still using original PVCs/DataVolumes

        Expected:
            - Migration fails as expected
            - All source PVCs/DataVolumes are retained (safety mechanism)
            - VMs continue running on original storage
        """
