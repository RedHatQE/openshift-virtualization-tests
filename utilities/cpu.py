import logging
import re
from typing import Set

from ocp_resources.node import Node
from ocp_resources.resource import Resource

from utilities.constants import (
    CPU_MODEL_LABEL_PREFIX,
    EXCLUDED_CPU_MODELS,
    EXCLUDED_OLD_CPU_MODELS,
    KUBERNETES_ARCH_LABEL,
)

LOGGER = logging.getLogger(__name__)
HOST_MODEL_CPU_LABEL = f"host-model-cpu.node.{Resource.ApiGroup.KUBEVIRT_IO}"


def get_nodes_cpu_model(nodes: list[Node]) -> dict[str, dict[str, Set[str]]]:
    """Checks the CPU model labels on each node and returns a dictionary of nodes and supported CPU models.

    Args:
        nodes: List of Node objects for which CPU model labels are to be checked.

    Returns:
        dict with two keys ("common" and "modern"), each containing a mapping of node names
        to sets of CPU model strings. "common" includes all non-excluded CPU models, while "modern"
        excludes old CPU models.
    """

    nodes_cpu_model: dict[str, dict[str, Set[str]]] = {"common": {}, "modern": {}}
    for node in nodes:
        nodes_cpu_model["common"][node.name] = set()
        nodes_cpu_model["modern"][node.name] = set()
        for label, value in node.labels.items():
            match_object = re.match(rf"{CPU_MODEL_LABEL_PREFIX}/(.*)", label)
            if (
                is_cpu_model_not_in_excluded_list(
                    filter_list=EXCLUDED_CPU_MODELS, match=match_object, label_value=value
                )
                and match_object
            ):
                nodes_cpu_model["common"][node.name].add(match_object.group(1))
            if (
                is_cpu_model_not_in_excluded_list(
                    filter_list=EXCLUDED_OLD_CPU_MODELS, match=match_object, label_value=value
                )
                and match_object
            ):
                nodes_cpu_model["modern"][node.name].add(match_object.group(1))
    return nodes_cpu_model


def is_cpu_model_not_in_excluded_list(filter_list: list[str], match: re.Match[str] | None, label_value: str) -> bool:
    """Checks if a CPU model is not in the excluded list.

    Args:
        filter_list: List of CPU model patterns to exclude.
        match: Regular expression match object containing the CPU model name in group 1.
        label_value: Value of the CPU model label (should be "true" for valid models).

    Returns:
        True if the CPU model is valid (match exists, label is "true", and not in excluded list),
        False otherwise.
    """
    return bool(match and label_value == "true" and not any(element in match.group(1) for element in filter_list))


def get_host_model_cpu(nodes: list[Node]) -> dict[str, str]:
    """Extracts the host model CPU from each node's labels.

    Args:
        nodes: List of Node objects to extract host model CPU information from.

    Returns:
        dict mapping node names to their host model CPU strings.

    Raises:
        AssertionError: If not all nodes have the host-model-cpu label.
    """
    nodes_host_model_cpu = {}
    for node in nodes:
        for label, value in node.labels.items():
            match_object = re.match(rf"{HOST_MODEL_CPU_LABEL}/(.*)", label)
            if match_object and value == "true":
                nodes_host_model_cpu[node.name] = match_object.group(1)
    assert len(nodes_host_model_cpu) == len(nodes), (
        f"All nodes did not have host-model-cpu label: {nodes_host_model_cpu} "
    )
    return nodes_host_model_cpu


def find_common_cpu_model_for_live_migration(cluster_cpu: str | None, host_cpu_model: dict[str, str]) -> str | None:
    """Finds a common CPU model for live migration across cluster nodes.

    Args:
        cluster_cpu: Common cluster CPU model string, or None if no common model exists.
        host_cpu_model: dict mapping node names to their host model CPU strings.

    Returns:
        Common CPU model string if needed for heterogeneous clusters, None if all nodes have
        the same host model CPU or if the cluster is heterogeneous with no common CPU.
    """
    if cluster_cpu:
        if len(set(host_cpu_model.values())) == 1:
            LOGGER.info(f"Host model cpus for all nodes are same {host_cpu_model}. No common cpus are needed")
            return None
        else:
            LOGGER.info(f"Using cluster node cpu: {cluster_cpu}")
            return cluster_cpu
    # if we reach here, it is heterogeneous cluster, we would return None
    LOGGER.warning("This is a heterogeneous cluster with no common cluster cpu.")
    return None


def get_common_cpu_from_nodes(cluster_cpus: Set[str]) -> str | None:
    """Receives a set of unique common CPUs between all schedulable nodes and returns one from the set.

    Args:
        cluster_cpus: Set of CPU model strings that are common across all schedulable nodes.

    Returns:
        A single CPU model string from the set if available, None if the set is empty.
    """
    common_cpu_model = next(iter(cluster_cpus)) if cluster_cpus else None
    LOGGER.info(f"Common CPU used is {common_cpu_model}")
    return common_cpu_model


def get_nodes_cpu_architecture(nodes: list[Node]) -> str:
    """Gets the CPU architecture from cluster nodes.

    Args:
        nodes: List of Node objects to extract architecture information from.

    Returns:
        CPU architecture string (e.g., "x86_64", "arm64", "s390x").

    Raises:
        AssertionError: If nodes have mixed CPU architectures.
    """
    nodes_cpu_arch = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
    assert len(nodes_cpu_arch) == 1, "Mixed CPU architectures in the cluster is not supported"
    return next(iter(nodes_cpu_arch))
