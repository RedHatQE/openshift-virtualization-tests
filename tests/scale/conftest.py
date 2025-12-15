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
from utilities.constants import TIMEOUT_20MIN, TIMEOUT_30SEC, UNPRIVILEGED_USER
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.operator import (
    get_machine_config_pool_by_name,
    get_machine_config_pools_conditions,
    get_mcp_updating_transition_times,
    wait_for_mcp_update_end,
    wait_for_mcp_update_start,
)
from utilities.virt import get_virt_handler_pods

LOGGER = logging.getLogger(__name__)

KUBE_API_QPS = 200
KUBE_API_BURST = 400


@pytest.fixture(scope="module")
def scale_client_configuration(request):  # skip-unused-code
    client_configuration = kubernetes.client.Configuration()
    client_configuration.connection_pool_maxsize = request.param["connection_pool_maxsize"]
    return client_configuration


@pytest.fixture(scope="module")
def scale_unprivileged_client(
    scale_client_configuration, skip_unprivileged_client, exported_kubeconfig, unprivileged_client
):  # skip-unused-code
    if skip_unprivileged_client:
        yield
    else:
        yield get_client(
            client_configuration=deepcopy(scale_client_configuration),
            config_file=exported_kubeconfig,
            context=get_user_kubeconfig_context(kubeconfig_filename=exported_kubeconfig, username=UNPRIVILEGED_USER),
        )


@pytest.fixture(scope="module")
def patched_hco_for_scale_testing(
    admin_client, hco_namespace, hyperconverged_resource_scope_module, cpu_for_migration
):  # skip-unused-code
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
def increased_open_file_limit(request):  # skip-unused-code
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
def virt_handler_pods(admin_client, hco_namespace):  # skip-unused-code
    return get_virt_handler_pods(client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="module")
def virt_handler_nodes(virt_handler_pods):  # skip-unused-code
    return [pod.node for pod in virt_handler_pods]


@pytest.fixture(scope="module")
def existing_pod_count(admin_client):  # skip-unused-code
    return len(list(Pod.get(dyn_client=admin_client)))


@pytest.fixture(scope="module")
def calculated_max_pods_per_virt_node(request, existing_pod_count, virt_handler_nodes):  # skip-unused-code
    assert virt_handler_nodes, "No virt-handler pods present"

    default_pods_per_node = 250
    total_pod_count = existing_pod_count + request.param["total_vm_count"]
    num_virt_handler_nodes = len(virt_handler_nodes)

    max_pods = math.ceil(
        total_pod_count / (num_virt_handler_nodes - 1) if num_virt_handler_nodes > 1 else total_pod_count
    )
    if default_pods_per_node > max_pods:
        max_pods = default_pods_per_node

    min_existing_max_pods_per_node = min([int(node.instance.status.capacity.pods) for node in virt_handler_nodes])
    if min_existing_max_pods_per_node > max_pods:
        max_pods = min_existing_max_pods_per_node

    return max_pods


@pytest.fixture(scope="module")
def created_kubeletconfigs_for_scale(
    request, calculated_max_pods_per_virt_node, workers, machine_config_pools
):  # skip-unused-code
    control_plane_mcp = get_machine_config_pool_by_name(mcp_name="master")
    worker_mcp = get_machine_config_pool_by_name(mcp_name="worker")

    initial_updating_transition_times = get_mcp_updating_transition_times(
        mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=machine_config_pools)
    )

    pause_mcps(paused=True, mcps=machine_config_pools)
    with KubeletConfig(
        name="test-custom-control-plane-kubelet-config",
        auto_sizing_reserved=True,
        kubelet_config={
            "nodeStatusMaxImages": -1,
            "kubeAPIQPS": KUBE_API_QPS,
            "kubeAPIBurst": KUBE_API_BURST,
        },
        machine_config_pool_selector={"matchLabels": {"custom-control-plane-kubelet": "enabled"}},
    ):
        with KubeletConfig(
            name="test-custom-worker-kubelet-config",
            auto_sizing_reserved=True,
            kubelet_config={
                "nodeStatusMaxImages": -1,
                "kubeAPIQPS": KUBE_API_QPS,
                "kubeAPIBurst": KUBE_API_BURST,
                "maxPods": calculated_max_pods_per_virt_node,
            },
            machine_config_pool_selector={"matchLabels": {"custom-worker-kubelet": "enabled"}},
        ):
            with label_mcps([control_plane_mcp], {"custom-control-plane-kubelet": "enabled"}):
                with label_mcps([worker_mcp], {"custom-worker-kubelet": "enabled"}):
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
