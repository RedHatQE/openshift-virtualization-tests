import collections
import logging

import bitmath
import pytest
from kubernetes.utils.quantity import parse_quantity
from ocp_resources.deployment import Deployment
from ocp_resources.pod_disruption_budget import PodDisruptionBudget
from ocp_resources.resource import Resource, ResourceEditor
from ocp_utilities.infra import get_pods_by_name_prefix

from tests.virt.node.descheduler.constants import (
    NODE_SELECTOR_LABEL,
    RUNNING_PING_PROCESS_NAME_IN_VM,
)
from tests.virt.node.descheduler.utils import (
    calculate_vm_deployment,
    create_kube_descheduler,
    deploy_vms,
    get_non_terminated_pods,
    get_pod_memory_requests,
    start_vms_with_process,
    vm_nodes,
    vms_per_nodes,
    wait_vmi_failover,
)
from tests.virt.utils import get_allocatable_memory_per_node, get_match_expressions_dict, start_stress_on_vm
from utilities.constants import TIMEOUT_5SEC
from utilities.infra import wait_for_pods_deletion
from utilities.virt import (
    node_mgmt_console,
    wait_for_node_schedulable_status,
)

LOGGER = logging.getLogger(__name__)


LOCALHOST = "localhost"


@pytest.fixture(scope="module")
def descheduler_long_lifecycle_profile(admin_client):
    with create_kube_descheduler(
        admin_client=admin_client,
        profiles=["LongLifecycle"],
        profile_customizations={
            "devLowNodeUtilizationThresholds": "High",  # underutilized <40%, overutilized >70%
            "devEnableEvictionsInBackground": True,
        },
    ) as kd:
        yield kd


@pytest.fixture(scope="module")
def descheduler_kubevirt_relieve_and_migrate_profile(
    admin_client,
    schedulable_nodes,
    nodes_taints_before_descheduler_test_run,
):
    with create_kube_descheduler(
        admin_client=admin_client,
        profiles=["DevKubeVirtRelieveAndMigrate"],
        profile_customizations={
            "devActualUtilizationProfile": "PrometheusCPUCombined",
        },
    ) as kd:
        yield kd


@pytest.fixture(scope="class")
def allocatable_memory_per_node_scope_class(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="module")
def cpu_capacity_per_node(schedulable_nodes):
    nodes_cpu = {}
    for node in schedulable_nodes:
        nodes_cpu[node] = int(parse_quantity(node.instance.status.capacity.cpu))
        LOGGER.info(f"Node {node.name} has total CPU capacity: {nodes_cpu[node]}")
    return nodes_cpu


@pytest.fixture(scope="module")
def vm_deployment_size(allocatable_memory_per_node_scope_session, cpu_capacity_per_node):
    vm_memory_size = next(iter(allocatable_memory_per_node_scope_session.values())) / 10
    LOGGER.info(f"VM memory is 10% from allocatable: {vm_memory_size.to_GiB()}")
    vm_cpu_size = max(1, next(iter(cpu_capacity_per_node.values())) // 20)
    LOGGER.info(f"VM CPU is 5% from capacity: {vm_cpu_size}")

    return {"cpu": vm_cpu_size, "memory": vm_memory_size}


@pytest.fixture(scope="class")
def calculated_vm_deployment_for_descheduler_test(
    request,
    schedulable_nodes,
    vm_deployment_size,
    available_memory_per_node,
):
    yield calculate_vm_deployment(
        available_memory_per_node=available_memory_per_node,
        deployment_size=vm_deployment_size,
        available_nodes=schedulable_nodes,
        percent_of_available_memory=request.param,
    )


@pytest.fixture(scope="class")
def deployed_vms_for_descheduler_test(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    vm_deployment_size,
    calculated_vm_deployment_for_descheduler_test,
):
    yield from deploy_vms(
        vm_prefix="vm-descheduler-test",
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=cpu_for_migration,
        vm_count=sum(calculated_vm_deployment_for_descheduler_test.values()),
        deployment_size=vm_deployment_size,
        descheduler_eviction=True,
    )


@pytest.fixture(scope="class")
def vms_orig_nodes_before_node_drain(deployed_vms_for_descheduler_test):
    return vm_nodes(vms=deployed_vms_for_descheduler_test)


@pytest.fixture(scope="class")
def vms_started_process_for_node_drain(
    deployed_vms_for_descheduler_test,
):
    return start_vms_with_process(
        vms=deployed_vms_for_descheduler_test,
        process_name=RUNNING_PING_PROCESS_NAME_IN_VM,
        args=LOCALHOST,
    )


@pytest.fixture(scope="class")
def node_to_drain(
    schedulable_nodes,
    vms_orig_nodes_before_node_drain,
):
    vm_per_node_counters = vms_per_nodes(vms=vms_orig_nodes_before_node_drain)
    for node in schedulable_nodes:
        if vm_per_node_counters[node.name] > 0:
            return node

    raise ValueError("No suitable node to drain")


@pytest.fixture()
def drain_uncordon_node(
    deployed_vms_for_descheduler_test,
    vms_orig_nodes_before_node_drain,
    node_to_drain,
):
    """Return when node is schedulable again after uncordon"""
    with node_mgmt_console(node=node_to_drain, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=node_to_drain, status=False)
        for vm in deployed_vms_for_descheduler_test:
            if vms_orig_nodes_before_node_drain[vm.name].name == node_to_drain.name:
                wait_vmi_failover(vm=vm, orig_node=vms_orig_nodes_before_node_drain[vm.name])


@pytest.fixture(scope="class")
def non_terminated_pods_per_node(admin_client, schedulable_nodes):
    return {node: get_non_terminated_pods(client=admin_client, node=node) for node in schedulable_nodes}


@pytest.fixture(scope="class")
def memory_requests_per_node(schedulable_nodes, non_terminated_pods_per_node):
    memory_requests = collections.defaultdict(bitmath.Byte)
    for node in schedulable_nodes:
        for pod in non_terminated_pods_per_node[node]:
            pod_instance = pod.exists
            if pod_instance:
                memory_requests[node] += get_pod_memory_requests(pod_instance=pod_instance)
    LOGGER.info(f"memory_requests collection: {memory_requests}")
    return memory_requests


@pytest.fixture(scope="class")
def available_memory_per_node(
    schedulable_nodes,
    allocatable_memory_per_node_scope_class,
    memory_requests_per_node,
):
    return {
        node: allocatable_memory_per_node_scope_class[node] - memory_requests_per_node[node]
        for node in schedulable_nodes
    }


@pytest.fixture(scope="class")
def node_with_most_available_memory(available_memory_per_node):
    return max(available_memory_per_node, key=available_memory_per_node.get)


@pytest.fixture(scope="class")
def node_with_least_available_memory(available_memory_per_node):
    return min(available_memory_per_node, key=available_memory_per_node.get)


@pytest.fixture(scope="class")
def node_labeled_for_test(node_with_least_available_memory):
    with ResourceEditor(patches={node_with_least_available_memory: {"metadata": {"labels": NODE_SELECTOR_LABEL}}}):
        yield node_with_least_available_memory


@pytest.fixture(scope="class")
def node_affinity_for_node_with_least_available_memory(node_with_least_available_memory):
    return {
        "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "preference": get_match_expressions_dict(nodes_list=[node_with_least_available_memory.hostname]),
                    "weight": 1,
                }
            ]
        }
    }


@pytest.fixture(scope="class")
def calculated_vm_deployment_for_node_with_least_available_memory(
    request,
    vm_deployment_size,
    available_memory_per_node,
    node_with_least_available_memory,
):
    yield calculate_vm_deployment(
        available_memory_per_node=available_memory_per_node,
        deployment_size=vm_deployment_size,
        available_nodes=[node_with_least_available_memory],
        percent_of_available_memory=request.param,
    )


@pytest.fixture(scope="class")
def deployed_vms_for_utilization_imbalance(
    request,
    namespace,
    unprivileged_client,
    cpu_for_migration,
    vm_deployment_size,
    calculated_vm_deployment_for_node_with_least_available_memory,
    node_affinity_for_node_with_least_available_memory,
):
    yield from deploy_vms(
        vm_prefix=request.param["vm_prefix"],
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=cpu_for_migration,
        vm_count=sum(calculated_vm_deployment_for_node_with_least_available_memory.values()),
        deployment_size=vm_deployment_size,
        descheduler_eviction=request.param["descheduler_eviction"],
        vm_affinity=node_affinity_for_node_with_least_available_memory,
    )


@pytest.fixture(scope="class")
def deployed_vms_on_labeled_node(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    vm_deployment_size,
    calculated_vm_deployment_for_node_with_least_available_memory,
):
    yield from deploy_vms(
        vm_prefix="node-labels-test",
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=cpu_for_migration,
        vm_count=sum(calculated_vm_deployment_for_node_with_least_available_memory.values()),
        deployment_size=vm_deployment_size,
        descheduler_eviction=True,
        node_selector_labels=NODE_SELECTOR_LABEL,
    )


@pytest.fixture(scope="class")
def vms_started_process_for_utilization_imbalance(
    deployed_vms_for_utilization_imbalance,
):
    return start_vms_with_process(
        vms=deployed_vms_for_utilization_imbalance,
        process_name=RUNNING_PING_PROCESS_NAME_IN_VM,
        args=LOCALHOST,
    )


@pytest.fixture(scope="class")
def unallocated_pod_count(
    admin_client,
    node_with_least_available_memory,
):
    non_terminated_pod_count = len(get_non_terminated_pods(client=admin_client, node=node_with_least_available_memory))
    return int(node_with_least_available_memory.instance.status.capacity.pods) - non_terminated_pod_count


@pytest.fixture(scope="class")
def utilization_imbalance(
    admin_client,
    namespace,
    node_with_least_available_memory,
    unallocated_pod_count,
):
    evict_protected_pod_label_dict = {"test-evict-protected-pod": "true"}
    evict_protected_pod_selector = {"matchLabels": evict_protected_pod_label_dict}

    utilization_imbalance_deployment_name = "utilization-imbalance-deployment"
    with PodDisruptionBudget(
        name=utilization_imbalance_deployment_name,
        namespace=namespace.name,
        min_available=unallocated_pod_count,
        selector=evict_protected_pod_selector,
    ):
        with Deployment(
            name=utilization_imbalance_deployment_name,
            namespace=namespace.name,
            client=admin_client,
            replicas=unallocated_pod_count,
            selector=evict_protected_pod_selector,
            template={
                "metadata": {
                    "labels": evict_protected_pod_label_dict,
                },
                "spec": {
                    "nodeSelector": {
                        f"{Resource.ApiGroup.KUBERNETES_IO}/hostname": node_with_least_available_memory.hostname,
                    },
                    "restartPolicy": "Always",
                    "containers": [
                        {
                            "name": "tail",
                            "image": "registry.access.redhat.com/ubi8/ubi-minimal:latest",
                            "command": ["/bin/tail"],
                            "args": ["-f", "/dev/null"],
                        }
                    ],
                },
            },
        ) as deployment:
            deployment.wait_for_replicas(timeout=unallocated_pod_count * TIMEOUT_5SEC)
            yield

    LOGGER.info(f"Wait while all {utilization_imbalance_deployment_name} pods removed")
    wait_for_pods_deletion(
        pods=get_pods_by_name_prefix(
            client=admin_client,
            namespace=namespace.name,
            pod_prefix=utilization_imbalance_deployment_name,
        )
    )


@pytest.fixture(scope="class")
def node_to_run_stress(schedulable_nodes, deployed_vms_for_descheduler_test):
    vm_per_node_counters = vms_per_nodes(vms=vm_nodes(vms=deployed_vms_for_descheduler_test))
    for node in schedulable_nodes:
        if vm_per_node_counters[node.name] > 0:
            return node

    raise ValueError("No suitable node to run stress")


@pytest.fixture(scope="class")
def stressed_vms_on_one_node(node_to_run_stress, deployed_vms_for_descheduler_test):
    stressed_vms_list = []
    for vm in deployed_vms_for_descheduler_test:
        if vm.vmi.node.name == node_to_run_stress.name:
            stressed_vms_list.append(vm)
            start_stress_on_vm(
                vm=vm,
                stress_command="nohup stress-ng --cpu 0 &> /dev/null &",
            )
    yield stressed_vms_list


@pytest.fixture(scope="module")
def nodes_taints_before_descheduler_test_run(nodes):
    nodes_taints_before = {node: node.instance.spec.taints for node in nodes}
    yield

    # clean up taints leftovers
    nodes_taints_after = {node: node.instance.spec.taints for node in nodes}
    for node in nodes_taints_before:
        if nodes_taints_after[node] != nodes_taints_before[node]:
            ResourceEditor(patches={node: {"spec": {"taints": nodes_taints_before[node]}}}).update()
