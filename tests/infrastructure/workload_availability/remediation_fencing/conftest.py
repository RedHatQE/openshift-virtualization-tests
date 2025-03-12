"""
Node Health Check common use cases
"""

import pytest
from ocp_resources.virtual_machine import VirtualMachine

from tests.infrastructure.workload_availability.remediation_fencing.constants import (
    NODE_HEALTH_DETECTION_OPERATOR,
    REMEDIATION_OPERATOR_NAMESPACE,
)
from tests.infrastructure.workload_availability.remediation_fencing.utils import perform_node_operation
from utilities.infra import get_utility_pods_from_nodes, is_jira_open
from utilities.operator import wait_for_csv_successful_state
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)


@pytest.fixture(scope="session")
def fail_if_compact_cluster_and_jira_47277_open(compact_cluster):
    if compact_cluster and is_jira_open(jira_id="CNV-47277"):
        pytest.fail("Test cannot run on compact cluster")


@pytest.fixture(scope="module")
def checkup_nodehealthcheck_operator_deployment(admin_client):
    wait_for_csv_successful_state(
        admin_client=admin_client,
        namespace_name=REMEDIATION_OPERATOR_NAMESPACE,
        subscription_name=NODE_HEALTH_DETECTION_OPERATOR,
    )


@pytest.fixture()
def nhc_vm_with_run_strategy_always(namespace, unprivileged_client):
    name = "nhc-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_node_before_failure(nhc_vm_with_run_strategy_always):
    return nhc_vm_with_run_strategy_always.vmi.node


@pytest.fixture()
def node_operation(request):
    return request.param


@pytest.fixture()
def refreshed_worker_utility_pods(admin_client, workers):
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture()
def performed_node_operation(nhc_vm_with_run_strategy_always, refreshed_worker_utility_pods, node_operation):
    """
    Performs node operations like node start/stop, node kubelet start/stop
    node reboot, node shutdown. After remediation action, utility pods are recreated.
    """
    perform_node_operation(
        utility_pods=refreshed_worker_utility_pods, node=nhc_vm_with_run_strategy_always.vmi.node, action=node_operation
    )
