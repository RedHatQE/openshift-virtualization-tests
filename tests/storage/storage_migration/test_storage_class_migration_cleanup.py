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

import pytest

from tests.storage.storage_migration.constants import (
    DELETE_SOURCE,
    KEEP_SOURCE,
    STORAGE_CLASS_MIGRATION_SOURCE,
    STORAGE_CLASS_MIGRATION_TARGET,
)
from tests.storage.storage_migration.utils import (
    verify_source_dvs_deleted,
    verify_source_dvs_exist,
    verify_vm_storage_class_updated,
)
from utilities.constants.pytest import QUARANTINED


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": STORAGE_CLASS_MIGRATION_SOURCE},
            {"target_storage_class": STORAGE_CLASS_MIGRATION_TARGET},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestStorageMigrationRetentionPolicy:
    """
    Test retentionPolicy functionality for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0, P1)

    Preconditions:
      - Running VM (online migration) with source PVC/DataVolume
      - Stopped VM (offline migration) with source PVC/DataVolume

    Steps:
      - Configure the retention policy at namespace level or at plan spec level
      - Execute the storage migration plan and wait for it to complete

    Expected:
      - The VM storage class is updated to the target, and source volumes are kept or
        deleted according to the configured retention policy
    """

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({}, id="default")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16297")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_retention_policy_default_behavior(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        """
        Verify default behavior keeps source volumes when retentionPolicy is not specified.

        STP Requirement: Default cleanup policy (P1)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume
            - Stopped VM (offline migration) with source PVC/DataVolume

        Steps:
            - Execute the migration plan without any retentionPolicy configured

        Expected:
            - Both VMs use the target storage class and their source volumes are kept
        """
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"ns_retention_policy": DELETE_SOURCE}, id="ns_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16298")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_delete_source(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
        combined_mode_mig_plan,
    ):
        """
        Verify namespace-level retentionPolicy=deleteSource deletes source volumes.

        STP Requirement: Namespace-level cleanup policy (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume
            - Stopped VM (offline migration) with source PVC/DataVolume

        Steps:
            - Execute the migration plan with namespace-level retentionPolicy=deleteSource

        Expected:
            - Both VMs use the target storage class, their source volumes are deleted, and
              the migration plan remains available after cleanup
        """
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs
        )
        assert combined_mode_mig_plan.exists, (
            f"Migration plan {combined_mode_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"spec_retention_policy": DELETE_SOURCE}, id="spec_delete")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16299")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_delete_source(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
        combined_mode_mig_plan,
    ):
        """
        Verify plan-level retentionPolicy=deleteSource deletes source volumes.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume
            - Stopped VM (offline migration) with source PVC/DataVolume

        Steps:
            - Execute the migration plan with plan-level (spec) retentionPolicy=deleteSource

        Expected:
            - Both VMs use the target storage class, their source volumes are deleted, and
              the migration plan remains available after cleanup
        """
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs
        )
        assert combined_mode_mig_plan.exists, (
            f"Migration plan {combined_mode_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"ns_retention_policy": KEEP_SOURCE}, id="ns_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16301")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_keep_source(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        """
        Verify namespace-level retentionPolicy=keepSource keeps source volumes.

        STP Requirement: Namespace-level cleanup policy (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume
            - Stopped VM (offline migration) with source PVC/DataVolume

        Steps:
            - Execute the migration plan with namespace-level retentionPolicy=keepSource

        Expected:
            - Both VMs use the target storage class and their source volumes are kept
        """
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)

    @pytest.mark.parametrize(
        "combined_mode_mig_plan",
        [pytest.param({"spec_retention_policy": KEEP_SOURCE}, id="spec_keep")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16302")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_keep_source(
        self,
        combined_mode_running_vm,
        ready_combined_mode_stopped_vm,
        target_storage_class,
        combined_mode_running_vm_source_dvs,
        combined_mode_stopped_vm_source_dvs,
    ):
        """
        Verify plan-level retentionPolicy=keepSource keeps source volumes.

        STP Requirement: Plan-level cleanup policy (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume
            - Stopped VM (offline migration) with source PVC/DataVolume

        Steps:
            - Execute the migration plan with plan-level (spec) retentionPolicy=keepSource

        Expected:
            - Both VMs use the target storage class and their source volumes are kept
        """
        verify_vm_storage_class_updated(vm=combined_mode_running_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=combined_mode_running_vm, source_dv_names=combined_mode_running_vm_source_dvs)
        verify_vm_storage_class_updated(vm=ready_combined_mode_stopped_vm, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=ready_combined_mode_stopped_vm, source_dv_names=combined_mode_stopped_vm_source_dvs)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": STORAGE_CLASS_MIGRATION_SOURCE},
            {"target_storage_class": STORAGE_CLASS_MIGRATION_TARGET},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestStorageMigrationCombinedRetentionPolicy:
    """
    Test combination of retentionPolicy for MultiNamespaceVirtualMachineStorageMigrationPlan.

    STP Traceability: CNV-73509 (P0)
    Note: Namespace-level policy overrides plan-level policy for that namespace.

    Preconditions:
      - Running VM (online migration) with source PVC/DataVolume in first namespace
      - Stopped VM (offline migration) with source PVC/DataVolume in second namespace

    Steps:
      - Configure conflicting retention policies at namespace level and at plan spec level
      - Execute the storage migration plan and wait for it to complete

    Expected:
      - The VM storage class is updated to the target, and the namespace-level retention
        policy takes precedence over the plan-level policy for that namespace
    """

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": KEEP_SOURCE, "ns_override_retention_policy": DELETE_SOURCE},
                id="spec_keep_ns_delete",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16305")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_delete_overrides_plan_keep(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        """
        Verify namespace-level deleteSource overrides plan-level keepSource for that namespace.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume in first namespace
            - Stopped VM (offline migration) with source PVC/DataVolume in second namespace

        Steps:
            - Execute the migration plan with plan-level retentionPolicy=keepSource and
              namespace-level retentionPolicy=deleteSource for the first namespace

        Expected:
            - Source volumes in the namespace with deleteSource are deleted while source
              volumes in the namespace without a namespace-level policy are kept (plan-level
              keepSource), and the migration plan remains available after cleanup
        """
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": DELETE_SOURCE, "ns_override_retention_policy": KEEP_SOURCE},
                id="spec_delete_ns_keep",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Product bug found, the namespace level retention policy is not applied, CNV-96425",
        run=False,
    )
    @pytest.mark.polarion("CNV-16306")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_keep_overrides_plan_delete(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        """
        Verify namespace-level keepSource overrides plan-level deleteSource for that namespace.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume in first namespace
            - Stopped VM (offline migration) with source PVC/DataVolume in second namespace

        Steps:
            - Execute the migration plan with plan-level retentionPolicy=deleteSource and
              namespace-level retentionPolicy=keepSource for the first namespace

        Expected:
            - Source volumes in the namespace with keepSource are kept (namespace overrides
              plan) while source volumes in the namespace without a namespace-level policy are
              deleted (plan-level deleteSource), and the migration plan remains available after
              cleanup
        """
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": DELETE_SOURCE, "ns_override_retention_policy": DELETE_SOURCE},
                id="both_delete",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16307")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_delete_source_retention_policy(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
        combined_policy_mig_plan,
    ):
        """
        Verify namespace-level and plan-level deleteSource together delete all source volumes.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume in first namespace
            - Stopped VM (offline migration) with source PVC/DataVolume in second namespace

        Steps:
            - Execute the migration plan with plan-level retentionPolicy=deleteSource and
              namespace-level retentionPolicy=deleteSource for the first namespace

        Expected:
            - All source volumes are deleted and the migration plan remains available after
              cleanup
        """
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )
        assert combined_policy_mig_plan.exists, (
            f"Migration plan {combined_policy_mig_plan.name} should still exist after cleanup"
        )

    @pytest.mark.parametrize(
        "combined_policy_mig_plan",
        [
            pytest.param(
                {"spec_retention_policy": KEEP_SOURCE, "ns_override_retention_policy": KEEP_SOURCE},
                id="both_keep",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16308")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_keep_source_retention_policy(
        self,
        combined_policy_vm_first_ns,
        combined_policy_vm_second_ns,
        target_storage_class,
        combined_policy_source_dv_names_first_ns,
        combined_policy_source_dv_names_second_ns,
    ):
        """
        Verify namespace-level and plan-level keepSource together keep all source volumes.

        STP Requirement: Combined namespace and plan-level cleanup policies (P0)

        Preconditions:
            - Running VM (online migration) with source PVC/DataVolume in first namespace
            - Stopped VM (offline migration) with source PVC/DataVolume in second namespace

        Steps:
            - Execute the migration plan with plan-level retentionPolicy=keepSource and
              namespace-level retentionPolicy=keepSource for the first namespace

        Expected:
            - All source volumes are kept
        """
        verify_vm_storage_class_updated(vm=combined_policy_vm_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_first_ns, source_dv_names=combined_policy_source_dv_names_first_ns
        )
        verify_vm_storage_class_updated(vm=combined_policy_vm_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(
            vm=combined_policy_vm_second_ns, source_dv_names=combined_policy_source_dv_names_second_ns
        )


@pytest.mark.parametrize(
    "source_storage_class",
    [
        pytest.param(
            {"source_storage_class": STORAGE_CLASS_MIGRATION_SOURCE},
            id="source_a",
        ),
    ],
    indirect=True,
)
class TestStorageMigrationFailureRetentionPolicy:
    """
    [NEGATIVE] Test retentionPolicy behavior when migration fails.
    Source volumes should be retained regardless of retentionPolicy setting.

    STP Traceability: CNV-73509 (P2)

    Preconditions:
      - VM with source PVC/DataVolume
    """

    @pytest.mark.parametrize(
        "failure_mig_plan",
        [pytest.param({"retention_policy": DELETE_SOURCE}, id="delete_source")],
        indirect=True,
    )
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Not clarified Failing migration cases, wait for product clarification", run=False
    )
    @pytest.mark.polarion("CNV-16309")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_delete_source_policy(
        self,
        failure_test_vm,
        failure_source_dv_names,
    ):
        """
        [NEGATIVE] Verify source volumes are retained when migration fails with retentionPolicy=deleteSource.

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            - Execute a migration plan with plan-level retentionPolicy=deleteSource and an
              invalid target storage class, then wait for the migration to fail

        Expected:
            - Source volumes are retained despite the deleteSource policy
        """
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)

    @pytest.mark.parametrize(
        "failure_mig_plan",
        [pytest.param({"retention_policy": KEEP_SOURCE}, id="keep_source")],
        indirect=True,
    )
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Not clarified Failing migration cases, wait for product clarification", run=False
    )
    @pytest.mark.polarion("CNV-16310")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_keep_source_policy(
        self,
        failure_test_vm,
        failure_source_dv_names,
    ):
        """
        [NEGATIVE] Verify source volumes are retained when migration fails with retentionPolicy=keepSource.

        STP Requirement: Source volumes preserved on migration failure (P2)

        Preconditions:
            - VM with source PVC/DataVolume

        Steps:
            - Execute a migration plan with plan-level retentionPolicy=keepSource and an
              invalid target storage class, then wait for the migration to fail

        Expected:
            - Source volumes are retained
        """
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)
