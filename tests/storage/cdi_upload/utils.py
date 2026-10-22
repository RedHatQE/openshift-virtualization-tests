"""CDI upload test utilities."""

import logging
from collections.abc import Callable
from contextlib import ExitStack

from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.upload_token_request import UploadTokenRequest

import utilities.storage
from utilities.constants.timeouts import TIMEOUT_5MIN

LOGGER = logging.getLogger(__name__)
HTTP_OK = 200


def get_storage_profile_minimum_supported_pvc_size(storage_class_name: str, client: DynamicClient) -> str | None:
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


def upload_images_to_multiple_dvs(
    client: DynamicClient,
    namespace_name: str,
    storage_class: str,
    num_dvs: int,
    upload_file_path: str,
    wait_for_upload_response_code: Callable,
    expected_response_code: int = HTTP_OK,
) -> None:
    """Create multiple DataVolumes, wait for UPLOAD_READY, and upload images with detailed logging.

    Manages complete DV lifecycle: creation, status monitoring, and image upload with progress
    tracking and error context logging.

    Args:
        client: Kubernetes dynamic client
        namespace_name: Namespace where DVs will be created
        storage_class: Storage class for DVs
        num_dvs: Number of DataVolumes to create
        upload_file_path: Path to file to upload
        wait_for_upload_response_code: Function to wait for upload response
        expected_response_code: Expected HTTP response code (default 200 OK)
    """
    with ExitStack() as stack:
        dvs = []
        LOGGER.info(f"Creating {num_dvs} DataVolumes in {namespace_name} with {storage_class}")
        for index in range(num_dvs):
            dv = stack.enter_context(
                cm=utilities.storage.create_dv(
                    client=client,
                    source="upload",
                    dv_name=f"concurrent-upload-{index}",
                    namespace=namespace_name,
                    size="3Gi",
                    storage_class=storage_class,
                )
            )
            dvs.append(dv)
            LOGGER.info(f"Created DV {dv.name} ({index + 1}/{num_dvs})")

        # Wait for all DVs to be UPLOAD_READY
        LOGGER.info(f"Waiting for {len(dvs)} DataVolumes to reach UPLOAD_READY status")
        for dv in dvs:
            dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_5MIN)
            LOGGER.info(f"DV {dv.name} reached UPLOAD_READY status")

        # Upload to all DVs
        LOGGER.info(f"Starting upload to {len(dvs)} DataVolumes")
        for dv_index, dv in enumerate(dvs, start=1):
            with UploadTokenRequest(
                client=client,
                name=dv.name,
                namespace=namespace_name,
                pvc_name=dv.pvc.name,
            ) as utr:
                token = utr.create().status.token
                LOGGER.info(f"Uploading to {dv.name} ({dv_index}/{len(dvs)})")
                wait_for_upload_response_code(
                    token=token,
                    data=upload_file_path,
                    response_code=expected_response_code,
                )

        LOGGER.info(f"Successfully created and uploaded {len(dvs)} DataVolumes")
