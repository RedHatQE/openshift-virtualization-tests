from __future__ import annotations

import logging
import math
import resource
from copy import deepcopy

import kubernetes
import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubelet_config import KubeletConfig
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.pod import Pod
from ocp_resources.resource import get_client
from ocp_resources.ssp import SSP

from tests.scale.utils import get_user_kubeconfig_context, label_mcps, pause_mcps
from utilities.constants import TIMEOUT_20MIN, TIMEOUT_30SEC, UNPRIVILEGED_USER, VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import get_pods
from utilities.operator import (
    get_machine_config_pool_by_name,
    get_machine_config_pools_conditions,
    get_mcp_updating_transition_times,
    wait_for_mcp_update_end,
    wait_for_mcp_update_start,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def scale_client_configuration(request):
    client_configuration = kubernetes.client.Configuration()
    client_configuration.connection_pool_maxsize = request.param["connection_pool_maxsize"]
    return client_configuration


@pytest.fixture(scope="module")
def scale_unprivileged_client(
    scale_client_configuration, skip_unprivileged_client, exported_kubeconfig, unprivileged_client
):
    if skip_unprivileged_client:
        yield
    else:
        yield get_client(
            client_configuration=deepcopy(scale_client_configuration),
            config_file=exported_kubeconfig,
            context=get_user_kubeconfig_context(kubeconfig_filename=exported_kubeconfig, username=UNPRIVILEGED_USER),
        )


@pytest.fixture(scope="module")
def patched_hco_for_scale_testing(admin_client, hco_namespace, hyperconverged_resource_scope_module, cpu_for_migration):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {
                    "tuningPolicy": "highBurst",
                    "defaultCPUModel": cpu_for_migration,
                },
            },
        },
        list_resource_reconcile=[KubeVirt, CDI, SSP],
        wait_for_reconcile_post_update=True,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        yield


@pytest.fixture(scope="session")
def increased_open_file_limit(request):
    """
    If you use this fixture and still receive max open files errors
    then please raise the default limits on your system.
    The test code is properly raising and lowering limits,
    closing threads and files, your base limits are just too low.
    Run to see your current limits: `ulimit -H -n && ulimit -S -n`
    """
    nofile_hard_limit = request.param["nofile_hard_limit"]
    original_limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    new_limits = (nofile_hard_limit, nofile_hard_limit)
    if new_limits > original_limits:
        resource.setrlimit(resource.RLIMIT_NOFILE, new_limits)
        yield
        resource.setrlimit(resource.RLIMIT_NOFILE, original_limits)
    else:
        LOGGER.info(f"Current open file limits {original_limits} are greater than {new_limits}.")
        yield


@pytest.fixture(scope="module")
def virt_handler_pods(admin_client, hco_namespace):
    return get_pods(
        dyn_client=admin_client,
        namespace=hco_namespace,
        label=f"{Pod.ApiGroup.KUBEVIRT_IO}={VIRT_HANDLER}",
    )


@pytest.fixture(scope="module")
def virt_handler_nodes(virt_handler_pods):
    return [pod.node for pod in virt_handler_pods]


@pytest.fixture(scope="module")
def existing_pod_count(admin_client):
    return len(list(Pod.get(dyn_client=admin_client)))


@pytest.fixture(scope="module")
def calculated_max_vms_per_virt_node(request, existing_pod_count, virt_handler_nodes):
    assert virt_handler_nodes, "No virt-handler pods present"

    total_pod_count = existing_pod_count + request.param["total_vm_count"]
    max_pods = total_pod_count / (len(virt_handler_nodes) - 1)

    total_cores = 0
    existing_max_pods_per_node = {}
    for node in virt_handler_nodes:
        node_capacity = node.instance.status.capacity
        total_cores += int(node_capacity.cpu)
        existing_max_pods_per_node[node.name] = int(node_capacity.pods)

    pods_per_core = (total_pod_count / total_cores) * 2

    return dict(
        max_pods=math.ceil(max_pods),
        pods_per_core=math.ceil(pods_per_core),
        min_existing_max_pods_per_node=min(existing_max_pods_per_node.values()),
    )


@pytest.fixture(scope="module")
def created_kubeletconfigs_for_scale(request, calculated_max_vms_per_virt_node, workers, machine_config_pools):
    max_pods = calculated_max_vms_per_virt_node["max_pods"]
    pods_per_core = calculated_max_vms_per_virt_node["pods_per_core"]
    calculated_max_vms_per_virt_node["min_existing_max_pods_per_node"]

    control_plane_mcp = get_machine_config_pool_by_name(mcp_name="master")
    worker_mcp = get_machine_config_pool_by_name(mcp_name="worker")

    initial_updating_transition_times = get_mcp_updating_transition_times(
        mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=machine_config_pools)
    )

    pause_mcps(paused=True, mcps=machine_config_pools)
    with KubeletConfig(
        name="test-custom-kubelet-config",
        auto_sizing_reserved=True,
        kubelet_config={
            "nodeStatusMaxImages": -1,
            "kubeAPIQPS": 200,
            "kubeAPIBurst": 400,
        },
        machine_config_pool_selector={"matchLabels": {"custom-kubelet": "enabled"}},
    ):
        with KubeletConfig(
            name="test-custom-worker-max-pods",
            kubelet_config={
                "maxPods": max_pods,
                "podsPerCore": pods_per_core,
            },
            machine_config_pool_selector={"matchLabels": {"custom-worker-max-pods": "enabled"}},
        ):
            with label_mcps([control_plane_mcp, worker_mcp], {"custom-kubelet": "enabled"}):
                with label_mcps([worker_mcp], {"custom-worker-max-pods": "enabled"}):
                    pause_mcps(paused=False, mcps=machine_config_pools)
                    wait_for_mcp_update_start(
                        machine_config_pools_list=machine_config_pools,
                        initial_transition_times=initial_updating_transition_times,
                    )
                    wait_for_mcp_update_end(
                        machine_config_pools_list=machine_config_pools,
                        timeout=TIMEOUT_20MIN * len(workers),
                        sleep=TIMEOUT_30SEC,
                    )

                    yield
                    teardown_updating_transition_times = get_mcp_updating_transition_times(
                        mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=machine_config_pools)
                    )
                    pause_mcps(paused=True, mcps=machine_config_pools)

    pause_mcps(paused=False, mcps=machine_config_pools)
    wait_for_mcp_update_start(
        machine_config_pools_list=machine_config_pools,
        initial_transition_times=teardown_updating_transition_times,
    )
    wait_for_mcp_update_end(
        machine_config_pools_list=machine_config_pools,
        timeout=TIMEOUT_20MIN * len(workers),
        sleep=TIMEOUT_30SEC,
    )
