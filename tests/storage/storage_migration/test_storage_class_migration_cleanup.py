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

    @pytest.mark.polarion("CNV-16297")
    @pytest.mark.tier2
    def test_retention_policy_default_behavior(self):
        """
        Test that default behavior is keepSource when retentionPolicy is not specified.

        STP Requirement: Default cleanup behavior (P1)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan without retentionPolicy field
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (default keepSource behavior)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-16298")
    @pytest.mark.tier2
    def test_namespace_level_retention_policy_delete_source(self):
        """
        Test namespace-level retentionPolicy=deleteSource.

        STP Requirement: Namespace-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with namespace-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-16299")
    @pytest.mark.tier2
    def test_spec_level_retention_policy_delete_source(self):
        """
        Test plan-level retentionPolicy=deleteSource.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is deleted (plan-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-16301")
    @pytest.mark.tier2
    def test_namespace_level_retention_policy_keep_source(self):
        """
        Test namespace-level retentionPolicy=keepSource.

        STP Requirement: Namespace-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with namespace-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (namespace-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-16302")
    @pytest.mark.tier2
    def test_spec_level_retention_policy_keep_source(self):
        """
        Test plan-level retentionPolicy=keepSource.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

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

    @pytest.mark.polarion("CNV-16303")
    @pytest.mark.tier2
    def test_single_namespace_retention_policy_keep_source(self):
        """
        Test plan-level retentionPolicy=keepSource in single namespace plan.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Migration completes successfully
            - Source PVC/DataVolume is kept (plan-level policy)
            - VM is running on new storage
        """

    @pytest.mark.polarion("CNV-16304")
    @pytest.mark.tier2
    def test_single_namespace_retention_policy_delete_source(self):
        """
        Test plan-level retentionPolicy=deleteSource in single namespace plan.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

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
      - Two VMs with source PVCs/DataVolumes in separate namespaces

    """

    @pytest.mark.polarion("CNV-16305")
    @pytest.mark.tier2
    def test_combined_namespace_and_spec_level_retention_policy(self):
        """
        Test combination of namespace-level and plan-level retentionPolicy.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Namespace-level policy overrides plan-level policy for that namespace.

        Preconditions:
            - Two VMs with source PVCs/DataVolumes in separate namespaces

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource and namespace-level retentionPolicy=deleteSource for one namespace
            2. Wait for all migrations to complete successfully
            3. Verify both VMs are using new PVCs
            4. Check if source PVCs exist in both namespaces

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are deleted
            - Source PVCs in other namespaces are kept (plan-level policy)
        """

    @pytest.mark.polarion("CNV-16306")
    @pytest.mark.tier2
    def test_combined_namespace_keep_spec_delete(self):
        """
        Test combination: namespace-level keepSource + plan-level deleteSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Namespace-level policy overrides plan-level policy for that namespace.

        Preconditions:
            - Two VMs with source PVCs/DataVolumes in separate namespaces

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource and namespace-level retentionPolicy=keepSource for one namespace
            2. Wait for all migrations to complete successfully
            3. Verify both VMs are using new PVCs
            4. Check if source PVCs exist in both namespaces

        Expected:
            - All migrations complete successfully
            - Source PVCs in namespaces with namespace-level policy are kept (namespace overrides plan)
            - Source PVCs in other namespaces are deleted (plan-level policy)
        """

    @pytest.mark.polarion("CNV-16307")
    @pytest.mark.tier2
    def test_combined_both_delete(self):
        """
        Test combination: namespace-level deleteSource + plan-level deleteSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Both policies agree on deletion.

        Preconditions:
            - Two VMs with source PVCs/DataVolumes in separate namespaces

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource and namespace-level retentionPolicy=deleteSource for one namespace
            2. Wait for all migrations to complete successfully
            3. Verify both VMs are using new PVCs
            4. Check if source PVCs exist in both namespaces

        Expected:
            - All migrations complete successfully
            - All source PVCs are deleted
        """

    @pytest.mark.polarion("CNV-16308")
    @pytest.mark.tier2
    def test_combined_both_keep(self):
        """
        Test combination: namespace-level keepSource + plan-level keepSource.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)
        Both policies agree on retention.

        Preconditions:
            - Two VMs with source PVCs/DataVolumes in separate namespaces

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource and namespace-level retentionPolicy=keepSource for one namespace
            2. Wait for all migrations to complete successfully
            3. Verify both VMs are using new PVCs
            4. Check if source PVCs exist in both namespaces

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
    """

    @pytest.mark.polarion("CNV-16309")
    @pytest.mark.tier2
    def test_failed_migration_with_delete_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=deleteSource. [NEGATIVE]

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource and invalid target storage class
            2. Wait for migration to fail
            3. Check migration status
            4. Check if source PVC/DataVolume exists
            5. Verify VM volume references

        Expected:
            - Migration fails as expected
            - Source PVC/DataVolume is retained (safety mechanism)
            - VM continues running on original storage
        """

    @pytest.mark.polarion("CNV-16310")
    @pytest.mark.tier2
    def test_failed_migration_with_keep_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=keepSource. [NEGATIVE]

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create VirtualMachineStorageMigrationPlan with plan-level retentionPolicy=keepSource and invalid target storage class
            2. Wait for migration to fail
            3. Check migration status
            4. Check if source PVC/DataVolume exists
            5. Verify VM volume references

        Expected:
            - Migration fails as expected
            - Source PVC/DataVolume is retained (as per policy)
            - VM continues running on original storage
        """

    @pytest.mark.polarion("CNV-16311")
    @pytest.mark.tier2
    def test_failed_multi_namespace_migration_with_delete_source_policy(self):
        """
        Test that source PVCs are retained when MultiNamespace migration fails with retentionPolicy=deleteSource. [NEGATIVE]

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            - Two VMs with source PVCs/DataVolumes in separate namespaces

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan with plan-level retentionPolicy=deleteSource, namespace-level retentionPolicy=deleteSource for one namespace, and invalid target storage class
            2. Wait for migration to fail
            3. Check migration status for all VMs
            4. Check if all source PVCs/DataVolumes exist
            5. Verify VM volume references

        Expected:
            - Migration fails as expected
            - All source PVCs/DataVolumes are retained (safety mechanism)
            - VMs continue running on original storage
        """
