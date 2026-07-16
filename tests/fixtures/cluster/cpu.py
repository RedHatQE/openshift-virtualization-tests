"""Cluster CPU model and migration CPU fixtures."""

import pytest
from pytest_testconfig import config as py_config

from utilities.constants.architecture import ARM_64
from utilities.cpu import (
    find_common_cpu_model_for_live_migration,
    get_common_cpu_from_nodes,
    get_host_model_cpu,
    get_nodes_cpu_model,
)


@pytest.fixture(scope="session")
def nodes_cpu_architecture():
    return py_config.get("cpu_arch")


@pytest.fixture(scope="session")
def cluster_node_cpus(schedulable_nodes):
    return get_nodes_cpu_model(nodes=schedulable_nodes)


@pytest.fixture(scope="session")
def cluster_common_node_cpu(cluster_node_cpus):
    return get_common_cpu_from_nodes(cluster_cpus=set.intersection(*cluster_node_cpus.get("common").values()))


@pytest.fixture(scope="session")
def cluster_common_modern_node_cpu(cluster_node_cpus):
    return get_common_cpu_from_nodes(cluster_cpus=set.intersection(*cluster_node_cpus.get("modern").values()))


@pytest.fixture(scope="session")
def host_cpu_model(schedulable_nodes, nodes_cpu_architecture):
    return None if nodes_cpu_architecture == ARM_64 else get_host_model_cpu(nodes=schedulable_nodes)


@pytest.fixture(scope="session")
def cpu_for_migration(cluster_common_node_cpu, host_cpu_model, nodes_cpu_architecture):
    """Get a CPU model that is common for all nodes"""
    return (
        None
        if nodes_cpu_architecture == ARM_64
        else find_common_cpu_model_for_live_migration(
            cluster_cpu=cluster_common_node_cpu, host_cpu_model=host_cpu_model
        )
    )


@pytest.fixture(scope="session")
def modern_cpu_for_migration(cluster_common_modern_node_cpu, host_cpu_model, nodes_cpu_architecture):
    """Get a modern CPU model that is common for all nodes"""
    return (
        None
        if nodes_cpu_architecture == ARM_64
        else find_common_cpu_model_for_live_migration(
            cluster_cpu=cluster_common_modern_node_cpu, host_cpu_model=host_cpu_model
        )
    )


@pytest.fixture(scope="module")
def skip_if_no_common_cpu(cluster_common_node_cpu, nodes_cpu_architecture):
    if not cluster_common_node_cpu and nodes_cpu_architecture != ARM_64:
        pytest.skip("This is a heterogeneous cluster")


@pytest.fixture(scope="module")
def skip_if_no_common_modern_cpu(cluster_common_modern_node_cpu, nodes_cpu_architecture):
    if not cluster_common_modern_node_cpu and nodes_cpu_architecture != ARM_64:
        pytest.skip("This is a heterogeneous cluster")
