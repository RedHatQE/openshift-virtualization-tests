import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.network.checkup_framework.utils import assert_successful_dpdk_checkup
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.dpdk,
    pytest.mark.usefixtures(
        "patched_align_cpus",
        "patched_runtime_class",
        "dpdk_checkup_traffic_generator_service_account",
        "dpdk_checkup_configmap_role_binding",
        "dpdk_checkup_resources_role_binding",
    ),
]


@pytest.fixture(scope="module")
def patched_align_cpus(hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_module: {"spec": {"featureGates": {"alignCPUs": True}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="module")
def patched_runtime_class(hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_module: {"spec": {"defaultRuntimeClass": "performance-dpdk"}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.mark.polarion("CNV-9776")
def test_dpdk_checkup_when_destination_and_source_on_same_node(
    unprivileged_client,
    dpdk_checkup_namespace,
    dpdk_configmap_same_node,
    dpdk_job,
):
    assert_successful_dpdk_checkup(configmap=dpdk_configmap_same_node)


@pytest.mark.polarion("CNV-9779")
def test_dpdk_checkup_with_high_transfer_rate_same_node(
    unprivileged_client,
    dpdk_checkup_namespace,
    dpdk_high_traffic_configmap_same_node,
    dpdk_job,
):
    assert_successful_dpdk_checkup(
        configmap=dpdk_high_traffic_configmap_same_node,
    )


@pytest.mark.polarion("CNV-9786")
def test_dpdk_checkup_with_high_transfer_rate_different_nodes(
    unprivileged_client,
    dpdk_checkup_namespace,
    dpdk_high_traffic_configmap_different_node,
    dpdk_job,
):
    assert_successful_dpdk_checkup(
        configmap=dpdk_high_traffic_configmap_different_node,
    )
