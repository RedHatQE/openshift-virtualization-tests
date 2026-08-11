"""Cluster node and worker-pod fixtures."""

import logging
import os
import re

import bitmath
import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.machine import Machine
from ocp_resources.node import Node
from packaging.version import Version
from pytest_testconfig import config as py_config

from utilities.constants.cluster import (
    KUBERNETES_ARCH_LABEL,
    NODE_ROLE_KUBERNETES_IO,
    WORKER_NODE_LABEL_KEY,
    WORKERS_TYPE,
)
from utilities.constants.virt import NODE_HUGE_PAGES_1GI_KEY
from utilities.infra import ClusterHosts, ExecCommandOnPod, get_nodes_with_label
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
        client=worker_node1.client,
        name=worker_node1.machine_name,
        namespace=py_config["machine_api_namespace"],
    )
    if machine.exists:
        return machine
    raise ResourceNotFoundError(f"Machine object for {worker_node1.name} doesn't exists")


@pytest.fixture(scope="session")
def hugepages_gib_values(workers):
    """Return the list of hugepage sizes (in GiB) across all worker nodes."""
    return [
        int(bitmath.parse_string(value, strict=False).GiB)
        for worker in workers
        if (value := worker.instance.status.allocatable.get(NODE_HUGE_PAGES_1GI_KEY))
    ]


@pytest.fixture(scope="session")
def workers_rhcos_version(schedulable_nodes):
    """Returns a dict mapping each schedulable node name to its RHCOS version.

    Returns:
        dict[str, str]: Node name to RHCOS version (e.g. {"node-1": "10.2.20260408", ...}).
    """
    rhcos_version_re = re.compile(r"CoreOS\s+([\d.]+)")
    versions = {}
    for node in schedulable_nodes:
        os_image = node.instance.status.nodeInfo.osImage
        match = rhcos_version_re.search(string=os_image)
        assert match, f"Failed to parse RHCOS version from osImage '{os_image}' on node '{node.name}'"
        versions[node.name] = match.group(1)
    return versions


@pytest.fixture(scope="session")
def cluster_has_rhcos10_or_above(workers_rhcos_version):
    return any(Version(ver) >= Version("10") for ver in workers_rhcos_version.values())
