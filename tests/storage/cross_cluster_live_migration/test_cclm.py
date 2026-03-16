import pytest

from tests.storage.constants import TEST_FILE_CONTENT, TEST_FILE_NAME
from tests.storage.cross_cluster_live_migration.utils import (
    assert_vms_are_stopped,
    assert_vms_can_be_deleted,
    verify_compute_live_migration_after_cclm,
    verify_vms_boot_id_after_cross_cluster_live_migration,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants import TIMEOUT_10MIN

TESTS_CLASS_NAME_SEVERAL_VMS = "TestCCLMSeveralVMs"

pytestmark = [
    pytest.mark.cclm,
    pytest.mark.remote_cluster,
    pytest.mark.usefixtures(
        "remote_cluster_enabled_feature_gate_and_configured_hco_live_migration_network",
        "local_cluster_enabled_feature_gate_and_configured_hco_live_migration_network",
        "local_cluster_enabled_mtv_feature_gate_ocp_live_migration",
    ),
]


@pytest.mark.parametrize(
    "vms_for_cclm",
    [
        pytest.param(
            {
                "vms_fixtures": [
                    "vm_for_cclm_from_template_with_data_source",
                    "vm_for_cclm_with_instance_type",
                ]
            },
        )
    ],
    indirect=True,
)
class TestCCLMSeveralVMs:
    @pytest.mark.polarion("CNV-11995")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster")
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        written_file_to_vms_before_cclm,
        vms_boot_id_before_cclm,
        mtv_migration,
    ):
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-11910")
    def test_verify_vms_not_rebooted_after_migration(self, local_vms_after_cclm_migration, vms_boot_id_before_cclm):
        verify_vms_boot_id_after_cross_cluster_live_migration(
            local_vms=local_vms_after_cclm_migration, initial_boot_id=vms_boot_id_before_cclm
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-14332")
    def test_verify_file_persisted_after_migration(self, local_vms_after_cclm_migration):
        for vm in local_vms_after_cclm_migration:
            check_file_in_vm(
                vm=vm,
                file_name=TEST_FILE_NAME,
                file_content=TEST_FILE_CONTENT,
                username=vm.username,
                password=vm.password,
            )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-14333")
    def test_source_vms_are_stopped_after_cclm(self, vms_for_cclm):
        assert_vms_are_stopped(vms=vms_for_cclm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-12038")
    def test_compute_live_migrate_vms_after_cclm(self, local_vms_after_cclm_migration):
        verify_compute_live_migration_after_cclm(local_vms=local_vms_after_cclm_migration)

    @pytest.mark.polarion("CNV-14334")
    def test_source_vms_can_be_deleted(self, vms_for_cclm):
        assert_vms_can_be_deleted(vms=vms_for_cclm)
