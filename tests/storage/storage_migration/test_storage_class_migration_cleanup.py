"""Storage migration cleanup tests.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_cleanup.md
"""

import pytest
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_A, STORAGE_CLASS_B
from tests.storage.storage_migration.constants import DELETE_SOURCE, KEEP_SOURCE
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
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        )
    ],
    indirect=True,
)
class TestStorageMigrationRetentionPolicy:
    """Test successful retention-policy migrations."""

    @pytest.mark.parametrize("combined_mode_mig_plan", [pytest.param({}, id="default")], indirect=True)
    @pytest.mark.polarion("CNV-16297")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_retention_policy_default_behavior(
        self,
        running_vm_for_scmig_test_first_ns,
        stopped_vm_for_scmig_test_first_ns,
        target_storage_class,
        running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs,
    ):
        """Verify the default policy keeps source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, running_vm_for_scmig_test_source_dvs),
            (stopped_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_source_dvs),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_exist(vm=vm, source_dv_names=source_dvs)

    @pytest.mark.parametrize("combined_mode_mig_plan", [pytest.param({"ns_retention_policy": DELETE_SOURCE}, id="ns_delete")], indirect=True)
    @pytest.mark.polarion("CNV-16298")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_delete_source(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_first_ns,
        target_storage_class, running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs, combined_mode_mig_plan
    ):
        """Verify namespace-level deleteSource deletes source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, running_vm_for_scmig_test_source_dvs),
            (stopped_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_source_dvs),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_deleted(vm=vm, source_dv_names=source_dvs)
        assert combined_mode_mig_plan.exists

    @pytest.mark.parametrize("combined_mode_mig_plan", [pytest.param({"spec_retention_policy": DELETE_SOURCE}, id="spec_delete")], indirect=True)
    @pytest.mark.polarion("CNV-16299")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_delete_source(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_first_ns,
        target_storage_class, running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs, combined_mode_mig_plan
    ):
        """Verify plan-level deleteSource deletes source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, running_vm_for_scmig_test_source_dvs),
            (stopped_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_source_dvs),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_deleted(vm=vm, source_dv_names=source_dvs)
        assert combined_mode_mig_plan.exists

    @pytest.mark.parametrize("combined_mode_mig_plan", [pytest.param({"ns_retention_policy": KEEP_SOURCE}, id="ns_keep")], indirect=True)
    @pytest.mark.polarion("CNV-16301")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_namespace_level_retention_policy_keep_source(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_first_ns,
        target_storage_class, running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs
    ):
        """Verify namespace-level keepSource keeps source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, running_vm_for_scmig_test_source_dvs),
            (stopped_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_source_dvs),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_exist(vm=vm, source_dv_names=source_dvs)

    @pytest.mark.parametrize("combined_mode_mig_plan", [pytest.param({"spec_retention_policy": KEEP_SOURCE}, id="spec_keep")], indirect=True)
    @pytest.mark.polarion("CNV-16302")
    @pytest.mark.usefixtures("combined_mode_mig_migration")
    def test_spec_level_retention_policy_keep_source(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_first_ns,
        target_storage_class, running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs
    ):
        """Verify plan-level keepSource keeps source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, running_vm_for_scmig_test_source_dvs),
            (stopped_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_source_dvs),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_exist(vm=vm, source_dv_names=source_dvs)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        )
    ],
    indirect=True,
)
class TestStorageMigrationCombinedRetentionPolicy:
    """Test namespace-policy precedence."""

    @pytest.mark.parametrize("combined_policy_and_combined_mode_mig_plan", [pytest.param({"spec_retention_policy": KEEP_SOURCE, "first_ns_override_retention_policy": DELETE_SOURCE}, id="spec_keep_ns_delete")], indirect=True)
    @pytest.mark.polarion("CNV-16305")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_delete_overrides_plan_keep(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_second_ns,
        target_storage_class, source_dv_names_first_ns_for_scmig_test,
        source_dv_names_second_ns_for_scmig_test, combined_policy_and_combined_mode_mig_plan
    ):
        """Verify namespace deleteSource overrides plan keepSource."""
        verify_vm_storage_class_updated(vm=running_vm_for_scmig_test_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=running_vm_for_scmig_test_first_ns, source_dv_names=source_dv_names_first_ns_for_scmig_test)
        verify_vm_storage_class_updated(vm=stopped_vm_for_scmig_test_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=stopped_vm_for_scmig_test_second_ns, source_dv_names=source_dv_names_second_ns_for_scmig_test)
        assert combined_policy_and_combined_mode_mig_plan.exists

    @pytest.mark.parametrize("combined_policy_and_combined_mode_mig_plan", [pytest.param({"spec_retention_policy": DELETE_SOURCE, "first_ns_override_retention_policy": KEEP_SOURCE}, id="spec_delete_ns_keep")], indirect=True)
    @pytest.mark.xfail(reason=f"{QUARANTINED}: namespace retention policy is not applied, CNV-96425", run=False)
    @pytest.mark.polarion("CNV-16306")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_keep_overrides_plan_delete(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_second_ns,
        target_storage_class, source_dv_names_first_ns_for_scmig_test,
        source_dv_names_second_ns_for_scmig_test, combined_policy_and_combined_mode_mig_plan
    ):
        """Verify namespace keepSource overrides plan deleteSource."""
        verify_vm_storage_class_updated(vm=running_vm_for_scmig_test_first_ns, target_storage_class=target_storage_class)
        verify_source_dvs_exist(vm=running_vm_for_scmig_test_first_ns, source_dv_names=source_dv_names_first_ns_for_scmig_test)
        verify_vm_storage_class_updated(vm=stopped_vm_for_scmig_test_second_ns, target_storage_class=target_storage_class)
        verify_source_dvs_deleted(vm=stopped_vm_for_scmig_test_second_ns, source_dv_names=source_dv_names_second_ns_for_scmig_test)
        assert combined_policy_and_combined_mode_mig_plan.exists

    @pytest.mark.parametrize("combined_policy_and_combined_mode_mig_plan", [pytest.param({"spec_retention_policy": DELETE_SOURCE, "first_ns_override_retention_policy": DELETE_SOURCE}, id="both_delete")], indirect=True)
    @pytest.mark.polarion("CNV-16307")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_delete_source_retention_policy(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_second_ns,
        target_storage_class, source_dv_names_first_ns_for_scmig_test,
        source_dv_names_second_ns_for_scmig_test, combined_policy_and_combined_mode_mig_plan
    ):
        """Verify both deleteSource policies delete source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, source_dv_names_first_ns_for_scmig_test),
            (stopped_vm_for_scmig_test_second_ns, source_dv_names_second_ns_for_scmig_test),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_deleted(vm=vm, source_dv_names=source_dvs)
        assert combined_policy_and_combined_mode_mig_plan.exists

    @pytest.mark.parametrize("combined_policy_and_combined_mode_mig_plan", [pytest.param({"spec_retention_policy": KEEP_SOURCE, "first_ns_override_retention_policy": KEEP_SOURCE}, id="both_keep")], indirect=True)
    @pytest.mark.polarion("CNV-16308")
    @pytest.mark.usefixtures("combined_policy_mig_migration")
    def test_namespace_and_plan_level_keep_source_retention_policy(
        self, running_vm_for_scmig_test_first_ns, stopped_vm_for_scmig_test_second_ns,
        target_storage_class, source_dv_names_first_ns_for_scmig_test,
        source_dv_names_second_ns_for_scmig_test
    ):
        """Verify both keepSource policies keep source volumes."""
        for vm, source_dvs in (
            (running_vm_for_scmig_test_first_ns, source_dv_names_first_ns_for_scmig_test),
            (stopped_vm_for_scmig_test_second_ns, source_dv_names_second_ns_for_scmig_test),
        ):
            verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
            verify_source_dvs_exist(vm=vm, source_dv_names=source_dvs)


@pytest.mark.parametrize("source_storage_class", [pytest.param({"source_storage_class": py_config[STORAGE_CLASS_A]}, id="source_a")], indirect=True)
class TestStorageMigrationFailureRetentionPolicy:
    """[NEGATIVE] Test source-volume retention after failed migration."""

    @pytest.mark.parametrize("failure_mig_plan", [pytest.param({"retention_policy": DELETE_SOURCE}, id="delete_source")], indirect=True)
    @pytest.mark.xfail(reason=f"{QUARANTINED}: failing migration behavior is not clarified, CNV-98407", run=False)
    @pytest.mark.polarion("CNV-16309")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_delete_source_policy(self, failure_test_vm, failure_source_dv_names):
        """[NEGATIVE] Verify deleteSource retains volumes after failure."""
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)

    @pytest.mark.parametrize("failure_mig_plan", [pytest.param({"retention_policy": KEEP_SOURCE}, id="keep_source")], indirect=True)
    @pytest.mark.xfail(reason=f"{QUARANTINED}: failing migration behavior is not clarified, CNV-98407", run=False)
    @pytest.mark.polarion("CNV-16310")
    @pytest.mark.usefixtures("failure_mig_migration")
    def test_failed_migration_with_keep_source_policy(self, failure_test_vm, failure_source_dv_names):
        """[NEGATIVE] Verify keepSource retains volumes after failure."""
        verify_source_dvs_exist(vm=failure_test_vm, source_dv_names=failure_source_dv_names)
