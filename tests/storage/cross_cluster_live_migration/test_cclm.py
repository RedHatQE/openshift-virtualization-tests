import pytest

from tests.storage.cross_cluster_live_migration.utils import verify_compute_live_migration_after_cclm
from utilities.constants import TIMEOUT_10MIN

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
    @pytest.mark.polarion("CNV-12038")
    def test_compute_live_migrate_vms_after_cclm(self, admin_client, namespace, vms_for_cclm):
        verify_compute_live_migration_after_cclm(client=admin_client, namespace=namespace, vms_list=vms_for_cclm)


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
    def test_compute_live_migrate_vms_after_cclm(self, admin_client, namespace, vms_for_cclm):
        verify_compute_live_migration_after_cclm(client=admin_client, namespace=namespace, vms_list=vms_for_cclm)
