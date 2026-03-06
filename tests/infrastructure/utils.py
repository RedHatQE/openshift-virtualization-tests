import logging

from kubernetes.dynamic import DynamicClient
from ocp_resources.deployment import Deployment
from ocp_resources.kubelet_config import KubeletConfig
from ocp_resources.node import Node

from utilities.exceptions import ResourceMissingFieldError, ResourceValueError

LOGGER = logging.getLogger(__name__)


def node_for_vmi(admin_client, vmi):
    """Return the node running the given VMI, using admin client for cluster-scoped access."""
    return Node(client=admin_client, name=vmi.instance.status.nodeName)


def verify_tekton_operator_installed(client: DynamicClient) -> None:
    """Verify Tekton operator is installed and available.

    Args:
        client (DynamicClient): Kubernetes dynamic client used to query cluster resources.

    Raises:
        ResourceNotFoundError: If Tekton operator deployment is not found.
        TimeoutExpiredError: If Tekton operator is not ready within the timeout period.
    """
    LOGGER.info("Verifying Tekton operator is installed and available")
    tekton_deployment = Deployment(
        name="openshift-pipelines-operator",
        namespace="openshift-operators",
        client=client,
        ensure_exists=True,
    )
    tekton_deployment.wait_for_replicas()


def verify_numa_enabled(client: DynamicClient) -> None:
    """Verify cluster has static CPU manager policy configured.

    Args:
        client (DynamicClient): Kubernetes dynamic client used to query cluster resources.

    Raises:
        ResourceMissingFieldError: If required fields are missing.
        ResourceValueError: If cpuManagerPolicy has wrong value.
    """
    LOGGER.info("Verifying cluster has nodes with NUMA topology and static CPU manager policy")
    for config in KubeletConfig.get(client=client):
        kubelet_config = getattr(config.instance.spec, "kubeletConfig", None)
        if not kubelet_config:
            raise ResourceMissingFieldError(f"KubeletConfig '{config.name}' missing spec.kubeletConfig")

        policy = getattr(kubelet_config, "cpuManagerPolicy", None)
        if not policy:
            raise ResourceMissingFieldError(
                f"KubeletConfig '{config.name}' missing spec.kubeletConfig.cpuManagerPolicy"
            )

        if policy != "static":
            raise ResourceValueError(
                f"KubeletConfig '{config.name}' has cpuManagerPolicy '{policy}', expected 'static'"
            )
