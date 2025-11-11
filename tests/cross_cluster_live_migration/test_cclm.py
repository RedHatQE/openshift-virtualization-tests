import pytest

from utilities.constants import TIMEOUT_10MIN

TESTS_CLASS_NAME = "CCLM"

pytestmark = [
    pytest.mark.cclm,
    pytest.mark.remote_cluster,
    pytest.mark.usefixtures(
        "remote_cluster_enabled_feature_gate_and_configured_hco_live_migration_network",
        "local_cluster_enabled_feature_gate_and_configured_hco_live_migration_network",
        "local_cluster_enabled_mtv_feature_gate_ocp_live_migration",
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
