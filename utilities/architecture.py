import os

from ocp_resources.node import Node
from ocp_resources.resource import get_client


def get_cluster_architecture() -> str:
    """
    Returns cluster architecture.

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
        nodes: list[Node] = list(Node.get(dyn_client=get_client()))
        nodes_cpu_arch = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
        arch = next(iter(nodes_cpu_arch))

    arch = X86_64 if arch == AMD_64 else arch

    if arch not in (X86_64, ARM_64, S390X):
        raise ValueError(f"{arch} architecture in not supported")

    return arch


def is_s390x() -> bool:
    from utilities.constants import S390X

    return get_cluster_architecture() == S390X


def is_x86_64() -> bool:
    from utilities.constants import X86_64

    return get_cluster_architecture() == X86_64
