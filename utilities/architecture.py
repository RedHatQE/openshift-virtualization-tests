import os
from functools import cache

from ocp_resources.node import Node

from utilities.cluster import cache_admin_client
from utilities.exceptions import UnsupportedCPUArchitectureError


@cache
def get_cluster_architecture() -> set[str]:
    """
    Returns cluster architecture.

    To run in CI, where a cluster is not available, set `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH` env variable.

    Returns:
        set[str]: cluster architectures.
    """
    # Lazy import to avoid circular dependency
    # TODO: remove when/if utilities modules are refactored
    from utilities.constants import KUBERNETES_ARCH_LABEL

    # Needed for CI
    arch = os.environ.get("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH")

    if not arch:
        # cache_admin_client is used here as this function is used to get the architecture when initialing pytest config
        nodes: list[Node] = list(Node.get(client=cache_admin_client()))
        cluster_archs = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
        if not cluster_archs:
            raise UnsupportedCPUArchitectureError(
                "Cluster architecture could not be determined (no nodes found and env var unset)."
            )
        return cluster_archs

    return {arch}
