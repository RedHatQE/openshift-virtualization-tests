from ocp_resources.storage_profile import StorageProfile

CDI_KUBEVIRT_IO = "cdi.kubevirt.io"


def get_storage_profile_min_supported_pvc_size(
    storage_class_name: str,
    client,
) -> str | None:
    """
    Get the minimum supported PVC size for a given storage class.

    Args:
        storage_class_name (str): The name of the storage class.
        client: An ApiClient instance used to interact with the cluster.

    Returns:
        str | None: The value of the 'cdi.kubevirt.io/minimumSupportedPvcSize'
        annotation if it exists, otherwise None.
    """
    profile = StorageProfile(client=client, name=storage_class_name).instance
    annotations = getattr(profile.metadata, "annotations", None) or {}
    return annotations.get(f"{CDI_KUBEVIRT_IO}/minimumSupportedPvcSize")
