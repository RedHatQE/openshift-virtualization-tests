from typing import Optional

from ocp_resources.storage_profile import StorageProfile


def get_storage_profile_minimum_supported_pvc_size(storage_class_name: str) -> Optional[str]:
    """
    Get the minimum supported PVC size from the storage profile annotations.

    Args:
        storage_class_name: Name of the storage class to get the minimum PVC size for

    Returns:
        The minimum supported PVC size string (e.g., "1Gi") from the storage profile annotation
        'cdi.kubevirt.io/minimumSupportedPvcSize', or None if not set
    """
    storage_profile = StorageProfile(name=storage_class_name, ensure_exists=True)
    annotations = getattr(storage_profile.instance.metadata, "annotations", {}) or {}
    min_pvc_size = annotations.get("cdi.kubevirt.io/minimumSupportedPvcSize")
    return min_pvc_size
