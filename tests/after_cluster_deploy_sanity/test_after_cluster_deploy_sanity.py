import logging

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.namespace import Namespace
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_utilities.infra import assert_nodes_in_healthy_condition, assert_nodes_schedulable
from timeout_sampler import TimeoutSampler

from utilities.constants import KUBELET_READY_CONDITION, TIMEOUT_1MIN, TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.hco import get_installed_hco_csv, wait_for_hco_conditions
from utilities.infra import storage_sanity_check, wait_for_pods_running
from utilities.operator import wait_for_cluster_operator_stabilize
from utilities.storage import get_data_sources_managed_by_data_import_cron

# flake8: noqa: PID001
LOGGER = logging.getLogger(__name__)


def wait_for_terminating_pvc(admin_client):
    def _get_terminating_pvcs():
        terminating_pvcs = []
        for pvc in PersistentVolumeClaim.get(dyn_client=admin_client):
            if pvc.instance.status.phase == pvc.Status.TERMINATING:
                terminating_pvcs.append(pvc.name)
        return terminating_pvcs

    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=_get_terminating_pvcs,
        exceptions_dict={NotFoundError: [], AttributeError: []},
    ):
        if not sample:
            return
        else:
            LOGGER.warning(f"Following pvcs are in terminating state: {sample}")


@pytest.fixture(scope="session")
def hco_managed_data_import_crons(hyperconverged_resource_scope_session):
    return [
        template.metadata.name
        for template in hyperconverged_resource_scope_session.instance.status.dataImportCronTemplates
    ]


@pytest.fixture(scope="session")
def data_import_cron_managed_datasources(golden_images_namespace):
    return get_data_sources_managed_by_data_import_cron(namespace=golden_images_namespace.name)


@pytest.mark.cluster_health_check
def test_node_sanity(admin_client, nodes):
    assert_nodes_in_healthy_condition(nodes=nodes, healthy_node_condition_type=KUBELET_READY_CONDITION)
    assert_nodes_schedulable(nodes=nodes)


@pytest.mark.cluster_health_check
def test_pod_sanity(admin_client, hco_namespace, nmstate_namespace):
    for namespace_obj in [hco_namespace, nmstate_namespace]:
        wait_for_pods_running(
            admin_client=admin_client,
            namespace=namespace_obj,
        )


@pytest.mark.cluster_health_check
def test_hyperconverged_sanity(admin_client, hco_namespace):
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        list_dependent_crs_to_check=[CDI, NetworkAddonsConfig, KubeVirt],
    )


@pytest.mark.cluster_health_check
def test_storage_sanity(cluster_storage_classes_names):
    assert storage_sanity_check(cluster_storage_classes_names=cluster_storage_classes_names)


@pytest.mark.cluster_health_check
def test_boot_volume_health(
    golden_images_namespace, hco_managed_data_import_crons, data_import_cron_managed_datasources
):
    assert len(hco_managed_data_import_crons) == len(data_import_cron_managed_datasources)
    LOGGER.info(f"All dataimport crons: {hco_managed_data_import_crons}")
    # Ensure all the datasources are in ready condition
    for datasource in data_import_cron_managed_datasources:
        assert any(datasource.name in dic_name for dic_name in hco_managed_data_import_crons)
        datasource.wait_for_condition(
            condition=datasource.Condition.READY,
            status=datasource.Condition.Status.TRUE,
        )


@pytest.mark.cluster_health_check
def test_pvc_health(admin_client):
    not_bound = []
    is_terminating_pvcs = False
    for pvc in PersistentVolumeClaim.get(dyn_client=admin_client):
        pvc_instance = pvc.instance
        pvc_status = pvc_instance.status.phase
        LOGGER.info(f"PVC {pvc.name} is in {pvc_status} state")
        if pvc_status != pvc.Status.BOUND:
            pvc_name = pvc.name
            LOGGER.info(f"PVC {pvc_name} status: {pvc_status}")
            if pvc_name.startswith("prime-"):
                if pvc_status == "Lost":
                    continue
                if pvc_status == pvc.Status.TERMINATING:
                    is_terminating_pvcs = True
                    continue
            not_bound.append(pvc.name)
    assert not not_bound, f"Following pvcs are not in bound state {not_bound}"
    if is_terminating_pvcs:
        wait_for_terminating_pvc(admin_client=admin_client)


@pytest.mark.cluster_health_check
def test_namespace_health(admin_client):
    if errored_namespaces := [
        f"{ns.name} found in status {ns.status}"
        for ns in Namespace.get(dyn_client=admin_client)
        if ns.exists and ns.status != Namespace.Status.ACTIVE
    ]:
        pytest.fail(f"{errored_namespaces} found in not active state")


@pytest.mark.cluster_health_check
def test_cluster_operator_health(admin_client):
    failed_operators = wait_for_cluster_operator_stabilize(admin_client=admin_client, wait_timeout=TIMEOUT_10MIN)
    assert not failed_operators, f"Following cluster operators are in unhealthy conditions: {failed_operators}"


@pytest.mark.cluster_health_check
def test_machine_config_pool_health(admin_client):
    failed_mcps = []
    for mcp in MachineConfigPool.get(dyn_client=admin_client):
        mcp_instance = mcp.instance
        ready_count = mcp_instance.status.readyMachineCount
        machine_count = mcp_instance.status.machineCount
        if machine_count > 0:
            degraded_count = mcp_instance.status.degradedMachineCount
            LOGGER.info(f"MCP {mcp.name} has {ready_count}/{machine_count} nodes in ready state")
            if int(ready_count) != int(machine_count):
                failed_mcps.append(
                    f"mcp: {mcp.name}, degraded count: {degraded_count}, ready count: {ready_count},"
                    f" machine count: {machine_count}"
                )

    assert not failed_mcps, f"MCP health check failed due to: {failed_mcps}"


@pytest.mark.cluster_health_check
def test_csv_health(admin_client, hco_namespace):
    csv = get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)
    csv.wait_for_status(
        status=csv.Status.SUCCEEDED,
        timeout=TIMEOUT_5MIN,
        stop_status="fakestatus",  # to bypass intermittent FAILED status that is not permanent.
    )


@pytest.mark.cluster_health_check
def test_common_node_cpu_model(cluster_node_cpus, cluster_common_node_cpu, cluster_common_modern_node_cpu):
    assert cluster_common_node_cpu and cluster_common_modern_node_cpu, (
        f"This is a heterogeneous cluster with no common cpus: {cluster_node_cpus}"
    )
