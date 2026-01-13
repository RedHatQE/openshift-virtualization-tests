import logging
from typing import Optional

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import Resource
from ocp_resources.storage_profile import StorageProfile

LOGGER = logging.getLogger(__name__)


def get_storage_profile_minimum_supported_pvc_size(storage_class_name: str, client: DynamicClient) -> Optional[str]:
    """
    Get the minimum supported PVC size from the storage profile annotations.

    Args:
        storage_class_name: Name of the storage class to get the minimum PVC size for
        client: DynamicClient for API operations

    Returns:
        The minimum supported PVC size string (e.g., "1Gi") from the storage profile annotation
        'cdi.kubevirt.io/minimumSupportedPvcSize', or None if not set
    """
    storage_profile = StorageProfile(name=storage_class_name, client=client, ensure_exists=True)
    min_pvc_size = storage_profile.instance.metadata.get("annotations", {}).get(
        f"{Resource.ApiGroup.CDI_KUBEVIRT_IO}/minimumSupportedPvcSize"
    )
    LOGGER.info(f"Minimum supported PVC size from the StorageProfile: {min_pvc_size}")
    return min_pvc_size
