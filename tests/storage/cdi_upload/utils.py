"""CDI upload test utilities."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from typing import TYPE_CHECKING

from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.upload_token_request import UploadTokenRequest
from timeout_sampler import TimeoutSampler

from tests.storage.cdi_upload.constants import HTTP_OK
from tests.storage.stop_status_utils import dv_stop_status_restart_threshold
from tests.storage.utils import upload_image
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_5MIN
from utilities.storage import create_dv

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

LOGGER = logging.getLogger(__name__)


def wait_for_upload_response_code(
    token: str, data: str, response_code: int, client: DynamicClient | None = None, asynchronous: bool = False
) -> None:
    """Wait for upload to complete with expected response code.

    Args:
        token: Upload token from UploadTokenRequest.
        data: File/data to upload.
        response_code: Expected HTTP response code.
        client: Kubernetes dynamic client.
        asynchronous: Whether to use the async upload endpoint.
    """
    kwargs: dict[str, object] = {
        "wait_timeout": TIMEOUT_1MIN,
        "sleep": 5,
        "func": upload_image,
        "token": token,
        "data": data,
        "client": client,
    }
    if asynchronous:
        kwargs["asynchronous"] = asynchronous
    sampler = TimeoutSampler(**kwargs)
    for sample in sampler:
        if sample == response_code:
            LOGGER.info(f"Upload response code: {sample} (expected)")
            return
        LOGGER.info(f"Upload response code: {sample} (expecting {response_code})")


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
    expected_response_code: int = HTTP_OK,
) -> None:
    """Create multiple DataVolumes, upload images, and verify all complete successfully.

    Uses the async endpoint so CDI converts DataVolumes concurrently in the background.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Namespace where DVs will be created.
        storage_class: Storage class for DVs.
        num_dvs: Number of DataVolumes to create.
        upload_file_path: Path to file to upload.
        expected_response_code: Expected HTTP response code (default 200 OK).
    """
    with ExitStack() as stack:
        dvs = []
        for index in range(num_dvs):
            dv = stack.enter_context(
                cm=create_dv(
                    client=client,
                    source="upload",
                    dv_name=f"concurrent-upload-{index}",
                    namespace=namespace_name,
                    size="3Gi",
                    storage_class=storage_class,
                )
            )
            dvs.append(dv)

        for dv in dvs:
            dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_5MIN)

        # Sequential uploads via async endpoint; CDI converts DVs concurrently in the background
        for dv in dvs:
            with UploadTokenRequest(
                client=client,
                name=dv.name,
                namespace=namespace_name,
                pvc_name=dv.pvc.name,
            ) as upload_token_request:
                token = upload_token_request.create().status.token
                LOGGER.info(f"Uploading image to {dv.name}")
                wait_for_upload_response_code(
                    token=token,
                    data=upload_file_path,
                    response_code=expected_response_code,
                    asynchronous=True,
                    client=client,
                )

        # Wait for all DataVolumes to complete imports
        for dv in dvs:
            dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
