import logging

import pytest
from kubernetes.utils.quantity import parse_quantity
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from tests.virt.node.descheduler.constants import (
    STRESS_NG_CPU_LOAD_COMMAND,
    STRESS_NG_MEMORY_LOAD_COMMAND,
)
from tests.virt.node.descheduler.utils import (
    calculate_vm_deployment,
    deploy_vms,
    make_vms_evictable,
    stress_vms_on_node,
    vm_nodes,
    vms_per_nodes,
)
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.virt import wait_for_migration_finished

LOGGER = logging.getLogger(__name__)


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
    # VMs are deployed locked (prefer-no-eviction) so the descheduler does not rebalance
    # them during the initial scheduling imbalance; they are unlocked after stress is applied.
    yield from deploy_vms(
        vm_prefix="vm-descheduler-test",
        client=unprivileged_client,
        namespace_name=namespace.name,
        cpu_model=cpu_for_migration,
        vm_count=sum(calculated_vm_deployment_for_descheduler_test.values()),
        deployment_size=vm_deployment_size,
        exclude_from_descheduler=True,
    )


@pytest.fixture()
def all_existing_migrations_completed(admin_client, namespace):
    # Descheduler may trigger multiple migrations, need to wait when all succeeded
    for migration in VirtualMachineInstanceMigration.get(client=admin_client, namespace=namespace):
        wait_for_migration_finished(migration=migration, timeout=TIMEOUT_5MIN)


@pytest.fixture(scope="class")
def node_to_run_stress(schedulable_nodes, deployed_vms_for_descheduler_test):
    vm_per_node_counters = vms_per_nodes(vms=vm_nodes(vms=deployed_vms_for_descheduler_test))
    node_with_most_vms = max(schedulable_nodes, key=lambda node: vm_per_node_counters.get(node.name, 0))
    if vm_per_node_counters[node_with_most_vms.name] > 0:
        LOGGER.info(
            f"Node to run stress: {node_with_most_vms.name} with {vm_per_node_counters[node_with_most_vms.name]} VMs"
        )
        return node_with_most_vms

    raise ValueError("No suitable node to run stress")


@pytest.fixture(scope="class")
def stressed_vms_on_one_node(node_to_run_stress, deployed_vms_for_descheduler_test):
    yield stress_vms_on_node(
        vms=deployed_vms_for_descheduler_test,
        node=node_to_run_stress,
        stress_command=STRESS_NG_CPU_LOAD_COMMAND,
    )


@pytest.fixture(scope="class")
def memory_stressed_vms_on_one_node(node_to_run_stress, deployed_vms_for_descheduler_test):
    yield stress_vms_on_node(
        vms=deployed_vms_for_descheduler_test,
        node=node_to_run_stress,
        stress_command=STRESS_NG_MEMORY_LOAD_COMMAND,
    )


@pytest.fixture(scope="class")
def cpu_stressed_evictable_vms(deployed_vms_for_descheduler_test, stressed_vms_on_one_node):
    make_vms_evictable(vms=deployed_vms_for_descheduler_test)
    return stressed_vms_on_one_node


@pytest.fixture(scope="class")
def memory_stressed_evictable_vms(deployed_vms_for_descheduler_test, memory_stressed_vms_on_one_node):
    make_vms_evictable(vms=deployed_vms_for_descheduler_test)
    return memory_stressed_vms_on_one_node


@pytest.fixture()
def workers_psi_metric_values(prometheus, workers):
    workers_names_list = [worker.name for worker in workers]
    metric_output = prometheus.query_sampler(query="descheduler:combined_utilization_and_pressure:avg1m")
    return {
        item["metric"]["instance"]: float(item["value"][1]) * 100
        for item in metric_output
        if item["metric"]["instance"] in workers_names_list
    }
