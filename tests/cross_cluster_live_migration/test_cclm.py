import pytest
from pytest_testconfig import config as py_config


# Create VM in the remote cluster, write some data
# Migrate the VM to the local cluster
# Verify the data is present in the local cluster
# Delete the VM from the remote cluster


TESTS_CLASS_NAME = "CCLM"

pytestmark = [
    pytest.mark.cclm,
    pytest.mark.usefixtures(
        "enabled_feature_gate_for_decentralized_live_migration_remote_cluster",
        "enabled_feature_gate_for_decentralized_live_migration_local_cluster",
        "enabled_mtv_feature_gate_ocp_live_migration",
        "configured_hco_live_migration_network_remote_cluster",
        "configured_hco_live_migration_network_local_cluster",
    ),
]

@pytest.mark.parametrize(
    "",
    [
        pytest.param(
            {
                "": "",
            },
            id="",
        )
    ],
    indirect=True,
)
class TestCCLM:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_migrate_vm_from_remote_to_local_cluster")
    @pytest.mark.parametrize(
        "",
        [
            pytest.param(
                {"": ""},
                marks=pytest.mark.polarion("CNV-00000"),
                id="",
            )
        ],
        indirect=True,
    )
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
    ):
        pass