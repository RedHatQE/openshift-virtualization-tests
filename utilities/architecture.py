import os
import sys
from functools import cache

from ocp_resources.node import Node
from pytest_testconfig import config as py_config

from utilities.cluster import cache_admin_client
from utilities.exceptions import UnsupportedCPUArchitectureError


@cache
def get_cluster_architecture() -> set[str]:
    """
    Returns cluster architecture.

    To run in CI, where a cluster is not available, set `OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH` env variable.

    Returns:
        set[str]: cluster architectures.

    Raises:
        UnsupportedCPUArchitectureError: If unable to determine architecture.
    """
    # Lazy import to avoid circular dependency
    # TODO: remove when/if utilities modules are refactored
    from utilities.constants.cluster import KUBERNETES_ARCH_LABEL  # noqa: PLC0415

    # Needed for CI
    if arch := os.environ.get("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"):
        return set(arch.split(","))

    # Skip cluster connection for pytest flags that exit immediately without collecting tests
    _pytest_exit_flags = {"--help", "-h", "--version"}
    if not _pytest_exit_flags.isdisjoint(sys.argv):
        return {"amd64"}

    # cache_admin_client is used here as this function is used to get the architecture when initialing pytest config
    nodes: list[Node] = list(Node.get(client=cache_admin_client()))
    cluster_archs = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
    if not cluster_archs:
        raise UnsupportedCPUArchitectureError(
            "Cluster architecture could not be determined (no nodes found and env var unset)."
        )
    return cluster_archs


def get_multiarch_cpu_arch() -> str | None:
    """
    Returns the target CPU architecture on multiarch clusters with a single --cpu-arch.

    When --cpu-arch=ARCH1,ARCH2, py_config["cpu_arch"] is never set, so this returns None.

    Returns:
        str | None: The CPU architecture string (e.g. "arm64") if running on a multiarch
            cluster with a single target arch, None otherwise.
    """
    # Lazy import to avoid circular dependency
    # TODO: remove when/if utilities modules are refactored
    from utilities.constants.architecture import MULTIARCH  # noqa: PLC0415

    cpu_arch = py_config.get("cpu_arch")
    if cpu_arch and py_config.get("cluster_type") == MULTIARCH:
        return cpu_arch
    return None
