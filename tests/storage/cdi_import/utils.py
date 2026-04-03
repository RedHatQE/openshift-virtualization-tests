"""Helper utilities for CDI import tests."""

from ocp_resources.datavolume import DataVolume
from timeout_sampler import TimeoutSampler

from tests.storage.utils import get_importer_pod
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, TIMEOUT_20SEC


def get_importer_pod_node(importer_pod):
    """Get the node name where the importer pod is scheduled.

    Args:
        importer_pod: The importer pod resource.

    Returns:
        str: The node name where the pod is scheduled.
    """
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: importer_pod.instance.get("spec", {}).get(
            "nodeName",
        ),
    ):
        if sample:
            return sample


def wait_for_pvc_recreate(pvc, pvc_original_timestamp):
    """Wait for PVC to be recreated with a new timestamp.

    Args:
        pvc: The PVC resource to monitor.
        pvc_original_timestamp: The original creation timestamp to compare against.
    """
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_20SEC,
        sleep=1,
        func=lambda: pvc.instance.metadata.creationTimestamp != pvc_original_timestamp,
    ):
        if sample:
            break


def wait_dv_and_get_importer(dv, admin_client):
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
