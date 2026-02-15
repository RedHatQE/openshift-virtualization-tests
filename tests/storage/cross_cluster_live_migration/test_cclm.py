import pytest
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_B
from tests.storage.cross_cluster_live_migration.constants import (
    TEST_FILE_CONTENT,
    TEST_FILE_NAME,
)
from tests.storage.cross_cluster_live_migration.utils import (
    delete_file_in_vm,
    verify_compute_live_migration_after_cclm,
    verify_vms_boot_time_after_migration,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants import TIMEOUT_10MIN
from utilities.virt import running_vm

TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE = "CCLMvmFromTemplateWithDataSource"
TESTS_CLASS_NAME_VM_WITH_INSTANCE_TYPE = "CCLMvmWithInstanceType"

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
    "remote_cluster_source_storage_class, local_cluster_target_storage_class, vms_for_cclm",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_B]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {
                "vms_fixtures": [
                    "vm_for_cclm_from_template_with_data_source",
                    "vm_for_cclm_from_template_with_dv",
                    "vm_for_cclm_with_instance_type",
                ]
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("remote_cluster_source_storage_class", "local_cluster_target_storage_class")
class TestCCLMvmFromTemplateWithDataSource: # TODO rename test class 
    @pytest.mark.polarion("CNV-11910")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"
    )
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        written_file_to_vms_before_cclm,
        vms_boot_time_before_cclm,
        mtv_migration,
    ):
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-XXXXX")
    def test_verify_vms_boot_time_after_migration(self, local_vms_after_cclm_migration, vms_boot_time_before_cclm):
        verify_vms_boot_time_after_migration(
            local_vms=local_vms_after_cclm_migration, initial_boot_time=vms_boot_time_before_cclm
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-XXXXX")
    def test_verify_file_persisted_after_migration(self, local_vms_after_cclm_migration):
        for vm in local_vms_after_cclm_migration:
            check_file_in_vm(
                vm=vm,
                file_name=TEST_FILE_NAME,
                file_content=TEST_FILE_CONTENT,
                username=vm.username,
                password=vm.password,
            )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-12038")
    def test_compute_live_migrate_vms_after_cclm(self, local_vms_after_cclm_migration):
        verify_compute_live_migration_after_cclm(local_vms=local_vms_after_cclm_migration)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-XXXXX")
    def test_snapshot_and_restore_vms_after_cclm(self, unprivileged_client, local_vms_after_cclm_migration):
        for vm in local_vms_after_cclm_migration:
            # Create snapshot
            with VirtualMachineSnapshot(
                name=f"snapshot-{vm.name}",
                namespace=vm.namespace,
                vm_name=vm.name,
                client=unprivileged_client,
            ) as snapshot:
                snapshot.wait_snapshot_done()

                # Delete the file and verify deletion
                delete_file_in_vm(vm=vm, file_name=TEST_FILE_NAME, username=vm.username, password=vm.password)

                # Stop VM and restore from snapshot
                vm.stop(wait=True)
                with VirtualMachineRestore(
                    client=unprivileged_client,
                    name=f"restore-{vm.name}",
                    namespace=vm.namespace,
                    vm_name=vm.name,
                    snapshot_name=snapshot.name,
                ) as vm_restore:
                    vm_restore.wait_restore_done()
                    running_vm(vm=vm)

                    # Verify file exists after restore
                    check_file_in_vm(
                        vm=vm,
                        file_name=TEST_FILE_NAME,
                        file_content=TEST_FILE_CONTENT,
                        username=vm.username,
                        password=vm.password,
                    )

    @pytest.mark.polarion("CNV-XXXXX")
    def test_source_vms_can_be_deleted(self, vms_for_cclm):
        source_vms_failed_cleanup = {}
        for vm in vms_for_cclm:
            try:
                assert vm.clean_up(), f"Failed to clean up source VM {vm.name}"
            except Exception as cleanup_exception:
                source_vms_failed_cleanup[vm.name] = cleanup_exception
        assert not source_vms_failed_cleanup, f"Failed to clean up source VMs: {source_vms_failed_cleanup}"


@pytest.mark.parametrize(
    "vms_for_cclm",
    [
        pytest.param(
            {"vms_fixtures": ["vm_for_cclm_with_instance_type"]},
        ),
    ],
    indirect=True,
)
class TestCCLMvmWithInstanceType:
    @pytest.mark.polarion("CNV-12013")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME_VM_WITH_INSTANCE_TYPE}::test_migrate_vm_from_remote_to_local_cluster"
    )
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        mtv_migration,
    ):
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VM_WITH_INSTANCE_TYPE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-12474")
    def test_compute_live_migrate_vms_after_cclm(self, local_vms_after_cclm_migration):
        verify_compute_live_migration_after_cclm(local_vms=local_vms_after_cclm_migration)
