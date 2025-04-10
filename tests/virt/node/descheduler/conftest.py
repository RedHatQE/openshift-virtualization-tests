import collections
import logging

import bitmath
import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.machine_config import MachineConfig
from ocp_resources.pod_disruption_budget import PodDisruptionBudget
from ocp_resources.resource import Resource, ResourceEditor
from ocp_utilities.infra import get_pods_by_name_prefix

from tests.virt.node.descheduler.constants import (
    DESCHEDULER_NAMESPACE_NAME,
    NODE_SELECTOR_LABEL,
    RUNNING_PING_PROCESS_NAME_IN_VM,
)
from tests.virt.node.descheduler.utils import (
    calculate_vm_deployment,
    create_kube_descheduler,
    deploy_vms,
    get_allocatable_memory_per_node,
    get_non_terminated_pods,
    get_pod_memory_requests,
    start_vms_with_process,
    vm_nodes,
    vms_per_nodes,
    wait_vmi_failover,
)
from tests.virt.utils import get_match_expressions_dict, start_stress_on_vm
from utilities.constants import BREW_REGISTERY_SOURCE, TIMEOUT_5SEC, TIMEOUT_30MIN, TIMEOUT_30SEC
from utilities.infra import (
    check_pod_disruption_budget_for_completed_migrations,
    create_ns,
    wait_for_pods_deletion,
)
from utilities.operator import (
    create_catalog_source,
    create_operator_group,
    create_subscription,
    get_install_plan_from_subscription,
    wait_for_catalogsource_ready,
    wait_for_mcp_updated_condition_true,
    wait_for_operator_install,
)
from utilities.virt import (
    node_mgmt_console,
    wait_for_node_schedulable_status,
)

LOGGER = logging.getLogger(__name__)

DESCHEDULER_CATALOG_SOURCE = "descheduler-catalog"
DESCHEDULER_OPERATOR_DEPLOYMENT_NAME = "descheduler-operator"

LOCALHOST = "localhost"


@pytest.fixture(scope="module")
def skip_if_1tb_memory_or_more_node(allocatable_memory_per_node_scope_module):
    """
    One of QE BM setups has worker with 5 TiB RAM memory while rest workers
    has 120 GiB RAM. Test should be skipped on this cluster.
    """
    upper_memory_limit = bitmath.TiB(value=1)
    for node, memory in allocatable_memory_per_node_scope_module.items():
        if memory >= upper_memory_limit:
            pytest.skip(f"Cluster has node with at least {upper_memory_limit} RAM: {node.name}")


@pytest.fixture(scope="package")
def descheduler_namespace(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name=DESCHEDULER_NAMESPACE_NAME,
        labels={"openshift.io/cluster-monitoring": "true"},
    )


@pytest.fixture(scope="package")
def created_descheduler_operator_group(descheduler_namespace):
    descheduler_operator_group = create_operator_group(
        namespace_name=descheduler_namespace.name,
        operator_group_name=DESCHEDULER_OPERATOR_DEPLOYMENT_NAME,
        target_namespaces=[descheduler_namespace.name],
    )
    yield descheduler_operator_group
    descheduler_operator_group.clean_up()


@pytest.fixture(scope="package")
def catalog_source_fbc_image():
    # TODO: implement logic for getting latest fbc staging image

    iib = "975349"
    image = f"{BREW_REGISTERY_SOURCE}/rh-osbs/iib:{iib}"
    return image


@pytest.fixture(scope="package")
def descheduler_catalog_source(admin_client, catalog_source_fbc_image):
    catalog_source = create_catalog_source(
        catalog_name=DESCHEDULER_CATALOG_SOURCE,
        image=catalog_source_fbc_image,
        display_name="Descheduler Index Image",
    )
    wait_for_catalogsource_ready(
        admin_client=admin_client,
        catalog_name=DESCHEDULER_CATALOG_SOURCE,
    )
    yield catalog_source
    catalog_source.clean_up()


@pytest.fixture(scope="package")
def created_descheduler_subscription(
    descheduler_catalog_source,
    descheduler_namespace,
):
    descheduler_subscription = create_subscription(
        subscription_name=DESCHEDULER_OPERATOR_DEPLOYMENT_NAME,
        package_name="cluster-kube-descheduler-operator",
        namespace_name=descheduler_namespace.name,
        catalogsource_name=descheduler_catalog_source.name,
    )

    yield descheduler_subscription
    descheduler_subscription.clean_up()


@pytest.fixture(scope="package")
def subscription_with_descheduler_install_plan(created_descheduler_subscription):
    return get_install_plan_from_subscription(subscription=created_descheduler_subscription)


@pytest.fixture(scope="package")
def descheduler_install_plan_installed(
    admin_client,
    descheduler_namespace,
    created_descheduler_subscription,
    subscription_with_descheduler_install_plan,
):
    wait_for_operator_install(
        admin_client=admin_client,
        install_plan_name=subscription_with_descheduler_install_plan,
        namespace_name=descheduler_namespace.name,
        subscription_name=created_descheduler_subscription.name,
    )


@pytest.fixture(scope="package")
def installed_descheduler_operator(
    descheduler_namespace,
    created_descheduler_operator_group,
    descheduler_catalog_source,
    created_descheduler_subscription,
    descheduler_install_plan_installed,
):
    deployment = Deployment(
        name=DESCHEDULER_OPERATOR_DEPLOYMENT_NAME,
        namespace=descheduler_namespace.name,
    )
    deployment.wait()
    deployment.wait_for_replicas()
    yield deployment


@pytest.fixture(scope="module")
def descheduler_long_lifecycle_profile():
    with create_kube_descheduler(
        profiles=["LongLifecycle"],
        profile_customizations={
            "devLowNodeUtilizationThresholds": "High",  # underutilized <40%, overutilized >70%
            "devEnableEvictionsInBackground": True,
        },
    ) as kd:
        yield kd


@pytest.fixture(scope="module")
def descheduler_kubevirt_releave_and_migrate_profile(
    schedulable_nodes,
    nodes_taints_before_descheduler_test_run,
    # created_machine_config_with_psi_args,
):
    with create_kube_descheduler(
        profiles=["DevKubeVirtRelieveAndMigrate"],
        profile_customizations={
            "devLowNodeUtilizationThresholds": "Medium",  # underutilized <20%, overutilized >50%
            "devActualUtilizationProfile": "PrometheusCPUCombined",
        },
    ) as kd:
        yield kd


@pytest.fixture(scope="module")
def created_machine_config_with_psi_args(active_machine_config_pools):
    # TODO: remove this fixture, all nodes should have psi=1 before running descheduler tests

    mc_with_psi_list = []
    for mcp in active_machine_config_pools:
        mc = MachineConfig(
            name=f"99-{mcp.name}-psi-karg",
            label={"machineconfiguration.openshift.io/role": mcp.name},
            kernel_arguments=["psi=1"],
        )
        mc.create()
        mc_with_psi_list.append(mc)

    wait_for_mcp_updated_condition_true(
        machine_config_pools_list=active_machine_config_pools,
        timeout=TIMEOUT_30MIN,
        sleep=TIMEOUT_30SEC,
    )

    yield

    for mc in mc_with_psi_list:
        mc.clean_up()

    wait_for_mcp_updated_condition_true(
        machine_config_pools_list=active_machine_config_pools,
        timeout=TIMEOUT_30MIN,
        sleep=TIMEOUT_30SEC,
    )


@pytest.fixture(scope="module")
def allocatable_memory_per_node_scope_module(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="class")
def allocatable_memory_per_node_scope_class(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="module")
def cpu_capacity_per_node(schedulable_nodes):
    nodes_cpu = {}
    for node in schedulable_nodes:
        nodes_cpu[node] = int(node.instance.status.capacity.cpu)
        LOGGER.info(f"Node {node.name} has total CPU capacity: {nodes_cpu[node]}")
    return nodes_cpu


@pytest.fixture(scope="module")
def vm_deployment_size(allocatable_memory_per_node_scope_module, cpu_capacity_per_node):
    vm_memory_size = next(iter(allocatable_memory_per_node_scope_module.values())) / 10
    LOGGER.info(f"VM memory is 10% from allocatable: {vm_memory_size.to_GiB()}")
    vm_cpu_size = next(iter(cpu_capacity_per_node.values())) // 10
    LOGGER.info(f"VM CPU is 10% from capacity: {vm_cpu_size}")

    return {"cpu": vm_cpu_size, "memory": vm_memory_size}


@pytest.fixture(scope="class")
def calculated_vm_deployment_for_node_drain_test(
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
def deployed_vms_for_node_drain(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    vm_deployment_size,
    calculated_vm_deployment_for_node_drain_test,
):
    yield from deploy_vms(
        vm_prefix="node-drain-test",
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=cpu_for_migration,
        vm_count=sum(calculated_vm_deployment_for_node_drain_test.values()),
        deployment_size=vm_deployment_size,
        descheduler_eviction=True,
    )


@pytest.fixture(scope="class")
def vms_orig_nodes_before_node_drain(deployed_vms_for_node_drain):
    return vm_nodes(vms=deployed_vms_for_node_drain)


@pytest.fixture(scope="class")
def vms_started_process_for_node_drain(
    deployed_vms_for_node_drain,
):
    return start_vms_with_process(
        vms=deployed_vms_for_node_drain,
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
    deployed_vms_for_node_drain,
    vms_orig_nodes_before_node_drain,
    node_to_drain,
):
    """Return when node is schedulable again after uncordon"""
    with node_mgmt_console(node=node_to_drain, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=node_to_drain, status=False)
        for vm in deployed_vms_for_node_drain:
            if vms_orig_nodes_before_node_drain[vm.name].name == node_to_drain.name:
                wait_vmi_failover(vm=vm, orig_node=vms_orig_nodes_before_node_drain[vm.name])


@pytest.fixture()
def completed_migrations(admin_client, namespace):
    check_pod_disruption_budget_for_completed_migrations(admin_client=admin_client, namespace=namespace.name)


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
def stress_started_on_vms_for_psi_metrics(vm_deployment_size, deployed_vms_on_labeled_node):
    for vm in deployed_vms_on_labeled_node:
        start_stress_on_vm(
            vm=vm,
            stress_command="nohup stress-ng --cpu 0 &> /dev/null &",
        )


@pytest.fixture(scope="class")
def second_node_labeled_labeled_for_migration(node_with_most_available_memory):
    with ResourceEditor(patches={node_with_most_available_memory: {"metadata": {"labels": NODE_SELECTOR_LABEL}}}):
        yield


@pytest.fixture(scope="module")
def nodes_taints_before_descheduler_test_run(nodes):
    nodes_taints_before = {node: node.instance.spec.taints for node in nodes}
    yield

    # clean up taints leftovers
    nodes_taints_after = {node: node.instance.spec.taints for node in nodes}
    for node in nodes_taints_before:
        if nodes_taints_after[node] != nodes_taints_before[node]:
            ResourceEditor(patches={node: {"spec": {"taints": nodes_taints_before[node]}}}).update()
