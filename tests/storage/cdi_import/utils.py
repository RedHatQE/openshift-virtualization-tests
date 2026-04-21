"""Helper utilities for CDI import tests."""

from typing import TYPE_CHECKING

from ocp_resources.datavolume import DataVolume
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.utils import get_importer_pod
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, TIMEOUT_20SEC

if TYPE_CHECKING:
    from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
    from ocp_resources.pod import Pod
    from ocp_resources.resource import DynamicClient


def get_importer_pod_node(importer_pod: Pod) -> str:
    """Get the node name where the importer pod is scheduled.

    Args:
        importer_pod: The importer pod resource.

    Returns:
        str: The node name where the pod is scheduled.

    Raises:
        TimeoutExpiredError: If the importer pod is not scheduled within the timeout period.
    """
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: importer_pod.instance["spec"].get("nodeName"),
    ):
        if sample:
            return sample
    raise TimeoutExpiredError("Importer pod was not scheduled within the timeout period.")


def wait_for_pvc_recreate(pvc: PersistentVolumeClaim, pvc_creation_timestamp: str) -> None:
    """Wait for PVC to be recreated with a new timestamp.

    Args:
        pvc: The PVC resource to monitor.
        pvc_creation_timestamp: The original creation timestamp to compare against.

    Raises:
        TimeoutExpiredError: If the PVC is not recreated within the timeout period.
    """
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_20SEC,
        sleep=1,
        func=lambda: pvc.instance.metadata.creationTimestamp != pvc_creation_timestamp,
    ):
        if sample:
            return
    raise TimeoutExpiredError("PVC was not recreated within the timeout period.")


def wait_dv_and_get_importer(dv: DataVolume, admin_client: DynamicClient) -> Pod:
    """Wait for DataVolume import to start and get the importer pod.

    Args:
        dv: The DataVolume resource.
        admin_client: The admin client for accessing cluster resources.

    Returns:
        Pod: The importer pod resource.
    """
    dv.wait_for_status(
        status=DataVolume.Status.IMPORT_IN_PROGRESS,
        timeout=TIMEOUT_1MIN,
        stop_status=DataVolume.Status.SUCCEEDED,
    )
    return get_importer_pod(client=admin_client, namespace=dv.namespace)
