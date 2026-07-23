"""Cluster node and worker-pod fixtures."""

import logging
import os

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.machine import Machine
from ocp_resources.node import Node
from pytest_testconfig import config as py_config

from utilities.constants.cluster import (
    KUBERNETES_ARCH_LABEL,
    NODE_ROLE_KUBERNETES_IO,
    WORKER_NODE_LABEL_KEY,
    WORKERS_TYPE,
)
from utilities.infra import ClusterHosts, ExecCommandOnPod, get_nodes_with_label, get_utility_pods_from_nodes
from utilities.virt import kubernetes_taint_exists

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def nodes(admin_client):
    yield list(Node.get(client=admin_client))


@pytest.fixture(scope="session")
def schedulable_nodes(nodes, nodes_cpu_architecture):
    """Get nodes marked as schedulable by kubevirt.

    For multi-arch testing - filter nodes by the architecture being tested.
    """
    schedulable_label = "kubevirt.io/schedulable"
    schedulable = [
        node
        for node in nodes
        if schedulable_label in node.labels.keys()
        and node.labels[schedulable_label] == "true"
        and not node.instance.spec.unschedulable
        and not kubernetes_taint_exists(node)
        and node.kubelet_ready
        and (not nodes_cpu_architecture or node.labels.get(KUBERNETES_ARCH_LABEL) == nodes_cpu_architecture)
    ]

    LOGGER.info(
        f"Schedulable nodes: {[node.name for node in schedulable]}, node architecture: {nodes_cpu_architecture or 'all'}"
    )
    yield schedulable


@pytest.fixture(scope="session")
def workers(nodes):
    return get_nodes_with_label(nodes=nodes, label=WORKER_NODE_LABEL_KEY)


@pytest.fixture(scope="session")
def control_plane_nodes(nodes):
    return get_nodes_with_label(nodes=nodes, label=f"{NODE_ROLE_KUBERNETES_IO}/control-plane")


@pytest.fixture(scope="session")
def worker_node1(schedulable_nodes):
    # Get first worker nodes out of schedulable_nodes list
    return schedulable_nodes[0]


@pytest.fixture(scope="session")
def worker_node2(schedulable_nodes):
    # Get second worker nodes out of schedulable_nodes list
    return schedulable_nodes[1]


@pytest.fixture(scope="session")
def worker_node3(schedulable_nodes):
    # Get third worker nodes out of schedulable_nodes list
    return schedulable_nodes[2]


@pytest.fixture(scope="session")
def workers_type(workers_utility_pods, installing_cnv):
    if installing_cnv:
        return
    physical = ClusterHosts.Type.PHYSICAL
    virtual = ClusterHosts.Type.VIRTUAL
    for pod in workers_utility_pods:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=pod.node)
        out = pod_exec.exec(command="systemd-detect-virt", ignore_rc=True)
        if out == "none":
            LOGGER.info(f"Cluster workers are: {physical}")
            os.environ[WORKERS_TYPE] = physical
            return physical

    LOGGER.info(f"Cluster workers are: {virtual}")
    os.environ[WORKERS_TYPE] = virtual
    return virtual


@pytest.fixture(scope="session")
def worker_machine1(worker_node1):
    machine = Machine(
        name=worker_node1.machine_name,
        namespace=py_config["machine_api_namespace"],
    )
    if machine.exists:
        return machine
    raise ResourceNotFoundError(f"Machine object for {worker_node1.name} doesn't exists")


@pytest.fixture(scope="session")
def workers_utility_pods(admin_client, workers, utility_daemonset, installing_cnv):
    """
    Get utility pods from worker nodes.
    When the tests start we deploy a pod on every worker node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture(scope="session")
def control_plane_utility_pods(admin_client, installing_cnv, control_plane_nodes, utility_daemonset):
    """
    Get utility pods from control plane nodes.
    When the tests start we deploy a pod on every control plane node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return
    return get_utility_pods_from_nodes(
        nodes=control_plane_nodes,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )
