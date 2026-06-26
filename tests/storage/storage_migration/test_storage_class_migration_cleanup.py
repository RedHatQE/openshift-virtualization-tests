"""
Storage migration cleanup tests for storage migration plans.

Tests verify the retentionPolicy field functionality, which controls whether source DataVolumes/PVCs
are kept (keepSource) or deleted (deleteSource) after successful VM storage migration.

The retentionPolicy field can be configured at:
- Plan level (spec) for VirtualMachineStorageMigrationPlan (single namespace)
- Namespace level for MultiNamespaceVirtualMachineStorageMigrationPlan
- Plan level (spec) for MultiNamespaceVirtualMachineStorageMigrationPlan
- Combination of namespace and plan level for MultiNamespaceVirtualMachineStorageMigrationPlan
  (namespace-level overrides plan-level when both are configured)

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md

Test Tier: Tier 2 (all tests in this module)
"""

import pytest

__test__ = False


class TestStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0, P1)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_retention_policy_default_behavior(self):
        """
        Test that default behavior is keepSource when retentionPolicy is not specified.

        STP Requirement: Default cleanup behavior (P1)

        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan without retentionPolicy field
               (neither plan-level nor namespace-level)
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
    @pytest.mark.tier2
    def test_namespace_level_retention_policy_delete_source(self):
        """
        Test namespace-level retentionPolicy=deleteSource.

        STP Requirement: Namespace-level cleanup policy (P0)

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
    @pytest.mark.tier2
    def test_spec_level_retention_policy_delete_source(self):
        """
        Test plan-level retentionPolicy=deleteSource.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume is deleted
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted (plan-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_namespace_level_retention_policy_keep_source(self):
        """
        Test namespace-level retentionPolicy=keepSource.

        STP Requirement: Namespace-level cleanup policy (P0)

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
    @pytest.mark.tier2
    def test_spec_level_retention_policy_keep_source(self):
        """
        Test plan-level retentionPolicy=keepSource.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume still exists
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (plan-level policy)
            - VM is running on new storage
        """


class TestSingleNamespaceStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for VirtualMachineStorageMigrationPlan (single namespace).

    STP Traceability: CNV-73509 (P0)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_single_namespace_retention_policy_keep_source(self):
        """
        Test plan-level retentionPolicy=keepSource in single namespace plan.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume still exists
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (plan-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_single_namespace_retention_policy_delete_source(self):
        """
        Test plan-level retentionPolicy=deleteSource in single namespace plan.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
        Steps:
            1. Verify source PVC/DataVolume is deleted
        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted (plan-level policy)
            - VM is running on new storage
        """


class TestStorageMigrationCombinedRetentionPolicy:
    """
    Test combination of retentionPolicy for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0)
    Note: Namespace-level policy overrides plan-level policy for that namespace.

    Preconditions:
      1. Two VMs with source PVCs/DataVolumes
      2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
        - plan-level retentionPolicy=keepSource
        - namespace-level retentionPolicy=deleteSource for specific namespace
      3. Wait for all migrations to complete successfully
      4. Verify the two VMs are using new PVCs

    """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_combined_namespace_and_spec_level_retention_policy(self):
        """
        Test combination of namespace-level and plan-level retentionPolicy.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Namespace-level policy overrides plan-level policy for that namespace.

        Steps:
            1. Verify source PVCs in namespaces WITHOUT namespace-level policy are kept (plan-level policy)
            2. Verify source PVCs in namespaces WITH namespace-level policy=deleteSource are deleted

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are deleted
            - Source PVCs in other namespaces are kept (plan-level policy)
        """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_combined_namespace_keep_spec_delete(self):
        """
        Test combination: namespace-level keepSource + plan-level deleteSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Namespace-level policy overrides plan-level policy for that namespace.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - plan-level retentionPolicy=deleteSource
                - namespace-level retentionPolicy=keepSource for specific namespace
            3. Wait for all migrations to complete successfully
            4. Verify the two VMs are using new PVCs

        Steps:
            1. Verify source PVCs in namespaces WITHOUT namespace-level policy are deleted (plan-level policy)
            2. Verify source PVCs in namespaces WITH namespace-level policy=keepSource are kept

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are kept (namespace overrides plan)
            - Source PVCs in other namespaces are deleted (plan-level policy)
        """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_combined_both_delete(self):
        """
        Test combination: namespace-level deleteSource + plan-level deleteSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Both policies agree on deletion.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - plan-level retentionPolicy=deleteSource
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
    @pytest.mark.tier2
    def test_combined_both_keep(self):
        """
        Test combination: namespace-level keepSource + plan-level keepSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Both policies agree on retention.

        Preconditions:
            1. Two VMs with source PVCs/DataVolumes
            2. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - plan-level retentionPolicy=keepSource
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

    STP Traceability: CNV-73509 (P2)

    Preconditions:
      - VM with source PVC/DataVolume
      - Configuration that causes migration to fail
    """

    @pytest.mark.polarion("CNV-XXXXX")
    @pytest.mark.tier2
    def test_failed_migration_with_delete_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=deleteSource.

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource
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
    @pytest.mark.tier2
    def test_failed_migration_with_keep_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=keepSource.

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource
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
    @pytest.mark.tier2
    def test_failed_multi_namespace_migration_with_delete_source_policy(self):
        """
        Test that source PVCs are retained when MultiNamespace migration fails with retentionPolicy=deleteSource.

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with:
                - plan-level retentionPolicy=deleteSource
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
