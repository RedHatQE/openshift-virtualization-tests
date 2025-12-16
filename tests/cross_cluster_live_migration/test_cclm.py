import pytest

from utilities.constants import TIMEOUT_10MIN
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify

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
    "vms_for_cclm",
    [
        pytest.param(
            {"vms_fixtures": ["vm_for_cclm_from_template_with_data_source"]},
        )
    ],
    indirect=True,
)
class TestCCLMvmFromTemplateWithDataSource:
    @pytest.mark.polarion("CNV-11910")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"
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
        depends=[f"{TESTS_CLASS_NAME_VM_FROM_TEMPLATE_WITH_DATA_SOURCE}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-00000")
    def test_compute_live_migrate_vms_after_cclm(self, admin_client, namespace, vms_for_cclm):
        vms_failed_migration = {}
        for vm in vms_for_cclm:
            local_vm = VirtualMachineForTests(
                name=vm.name, namespace=namespace.name, client=admin_client, generate_unique_name=False
            )
            local_vm.username = vm.username
            local_vm.password = vm.password
            try:
                migrate_vm_and_verify(vm=local_vm, check_ssh_connectivity=True)
            except Exception as migration_exception:
                vms_failed_migration[local_vm.name] = migration_exception
        assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"


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
    @pytest.mark.polarion("CNV-00001")
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
    @pytest.mark.polarion("CNV-00002")
    def test_compute_live_migrate_vms_after_cclm(self, admin_client, namespace, vms_for_cclm):
        vms_failed_migration = {}
        for vm in vms_for_cclm:
            local_vm = VirtualMachineForTests(
                name=vm.name, namespace=namespace.name, client=admin_client, generate_unique_name=False
            )
            local_vm.username = vm.username
            local_vm.password = vm.password
            try:
                migrate_vm_and_verify(vm=local_vm, check_ssh_connectivity=True)
            except Exception as migration_exception:
                vms_failed_migration[local_vm.name] = migration_exception
        assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"
