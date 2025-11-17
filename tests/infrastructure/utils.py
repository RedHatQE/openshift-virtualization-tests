import logging

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.deployment import Deployment
from ocp_resources.kubelet_config import KubeletConfig

from utilities.exceptions import ResourceMissingFieldError, ResourceValueError

LOGGER = logging.getLogger(__name__)


def verify_tekton_operator_installed(client) -> None:
    """Verify Tekton operator is installed and available.

    Args:
        client: pass client argument

    Raises:
        ResourceNotFoundError: If Tekton operator is not installed or not ready.
    """
    LOGGER.info("Verifying Tekton operator is installed and available")
    tekton_deployment = Deployment(
        name="openshift-pipelines-operator",
        namespace="openshift-operators",
        client=client,
    )
    if not tekton_deployment.exists or tekton_deployment.instance.status.readyReplicas == 0:
        raise ResourceNotFoundError("Tekton operator is not installed or not ready. Cluster needs to be investigated")


def verify_numa_enabled(client) -> None:
    """Verify cluster has nodes with NUMA topology and static CPU manager policy.

    Args:
        client: pass client argument

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
