import pytest

from utilities.constants import TIMEOUT_10MIN

TESTS_CLASS_NAME = "CCLM"

pytestmark = [
    pytest.mark.cclm,
    pytest.mark.remote_cluster,
    pytest.mark.usefixtures(
        "enabled_feature_gate_for_decentralized_live_migration_remote_cluster",
        "enabled_feature_gate_for_decentralized_live_migration_local_cluster",
        "enabled_mtv_feature_gate_ocp_live_migration",
        "configured_hco_live_migration_network_remote_cluster",
        "configured_hco_live_migration_network_local_cluster",
        "mtv_provider_remote_cluster",
        "mtv_provider_local_cluster",
    ),
]


class TestCCLM:
    @pytest.mark.polarion("CNV-11910")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_migrate_vm_from_remote_to_local_cluster")
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        mtv_migration,
    ):
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
