import os

from ocp_resources.node import Node

from utilities.cluster import cache_admin_client


def get_cluster_architecture() -> str:
    """
    Returns cluster architecture.

    To run in CI, where a cluster is not available, set `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH` env variable.

    Returns:
        str: cluster architecture.

    Raises:
        ValueError: if architecture is not supported.
    """
    from utilities.constants import AMD_64, ARM_64, KUBERNETES_ARCH_LABEL, S390X, X86_64

    # Needed for CI
    arch = os.environ.get("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH")

    if not arch:
        # TODO: merge with `get_nodes_cpu_architecture`
        # cache_admin_client is used here as this function is used to get the architecture when initialing pytest config
        nodes: list[Node] = list(Node.get(dyn_client=cache_admin_client()))
        nodes_cpu_arch = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
        arch = next(iter(nodes_cpu_arch))

    arch = X86_64 if arch == AMD_64 else arch

    if arch not in (X86_64, ARM_64, S390X):
        raise ValueError(f"{arch} architecture in not supported")

    return arch
