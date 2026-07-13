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
"""

import pytest

__test__ = False


class TestStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0, P1)

    Parametrize:
        - migration_mode:
            - online (VM running during migration)
            - offline (VM stopped during migration)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-16297")
    def test_retention_policy_default_behavior(self):
        """
        Test that default behavior is keepSource when retentionPolicy is not specified.

        STP Requirement: Default cleanup policy (P1)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            1. Create MultiNamespaceVirtualMachineStorageMigrationPlan without retentionPolicy field
            2. Wait for migration to complete successfully
            3. Verify VM is using new PVC/DataVolume
            4. Check if source PVC/DataVolume exists

        Expected:
            - Source PVC/DataVolume is kept (default keepSource behavior)
        """

    @pytest.mark.polarion("CNV-16298")
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
            - Source PVC/DataVolume is deleted
        """

    @pytest.mark.polarion("CNV-16299")
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
            - Source PVC/DataVolume is deleted
        """

    @pytest.mark.polarion("CNV-16301")
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
            - Source PVC/DataVolume is kept
        """

    @pytest.mark.polarion("CNV-16302")
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
            - Source PVC/DataVolume is kept
        """


class TestSingleNamespaceStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for VirtualMachineStorageMigrationPlan (single namespace).

    STP Traceability: CNV-73509 (P0)

    Parametrize:
        - migration_mode:
            - online (VM running during migration)
            - offline (VM stopped during migration)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-16303")
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
            - Source PVC/DataVolume is kept
        """

    @pytest.mark.polarion("CNV-16304")
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
            - Source PVC/DataVolume is deleted
        """


class TestStorageMigrationCombinedRetentionPolicy:
    """
    Test combination of retentionPolicy for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0)
    Note: Namespace-level policy overrides plan-level policy for that namespace.

    Parametrize:
        - migration_mode:
            - online (both VMs running during migration)
            - offline (both VMs stopped during migration)
            - online+offline (one VM running, one VM stopped during migration)

    Preconditions:
      - Two VMs with source PVCs/DataVolumes in separate namespaces

    """

    @pytest.mark.polarion("CNV-16305")
    def test_namespace_delete_overrides_plan_keep(self):
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
            - Source PVCs in namespace with namespace-level deleteSource policy are deleted
            - Source PVCs in namespace without namespace-level policy are kept (plan-level keepSource)
        """

    @pytest.mark.polarion("CNV-16306")
    def test_namespace_keep_overrides_plan_delete(self):
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
            - Source PVCs in namespace with namespace-level keepSource policy are kept (namespace overrides plan)
            - Source PVCs in namespace without namespace-level policy are deleted (plan-level deleteSource)
        """

    @pytest.mark.polarion("CNV-16307")
    def test_namespace_and_plan_level_delete_source_retention_policy(self):
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
            - All source PVCs are deleted
        """

    @pytest.mark.polarion("CNV-16308")
    def test_namespace_and_plan_level_keep_source_retention_policy(self):
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
            - All source PVCs are kept
        """


class TestStorageMigrationFailureRetentionPolicy:
    """
    [NEGATIVE] Test retentionPolicy behavior when migration fails.
    Source volumes should be retained regardless of retentionPolicy setting.

    STP Traceability: CNV-73509 (P2)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.polarion("CNV-16309")
    def test_failed_migration_with_delete_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=deleteSource.

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
            - Source PVC/DataVolume is retained despite deleteSource policy
        """

    @pytest.mark.polarion("CNV-16310")
    def test_failed_migration_with_keep_source_policy(self):
        """
        Test that source PVC/DataVolume is retained when migration fails with retentionPolicy=keepSource.

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
            - Source PVC/DataVolume is retained
        """

    @pytest.mark.polarion("CNV-16311")
    def test_failed_multi_namespace_migration_with_delete_source_policy(self):
        """
        Test that source PVCs are retained when MultiNamespace migration fails with retentionPolicy=deleteSource.

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
            - All source PVCs/DataVolumes are retained despite deleteSource policies
        """
