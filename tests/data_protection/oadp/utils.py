from __future__ import annotations

import logging
import shlex

from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from utilities.constants.namespaces import NamespacesNames
from utilities.constants.timeouts import TIMEOUT_10SEC, TIMEOUT_15SEC
from utilities.infra import get_pod_by_name_prefix

LOGGER = logging.getLogger(__name__)

FILE_PATH_FOR_WINDOWS_BACKUP = "C:/oadp_file_before_backup.txt"


def wait_for_restored_dv(dv: DataVolume) -> None:
    """
    Wait for a restored DataVolume to be ready after OADP restore.

    Args:
        dv: DataVolume to wait for

    Raises:
        TimeoutExpiredError: If PVC does not reach BOUND status within 15 seconds
            or DataVolume does not succeed within 10 seconds
    """
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


def get_velero_backup_logs(backup_name: str, client: DynamicClient) -> str:
    """Retrieve Velero backup logs by executing the velero CLI inside the velero pod.

    Args:
        backup_name: Name of the Velero backup to retrieve logs for.
        client: OpenShift dynamic client.

    Returns:
        The raw log output from the velero backup logs command.
    """
    LOGGER.info(f"Retrieving Velero backup logs for backup: {backup_name}")
    velero_pod = get_pod_by_name_prefix(client=client, pod_prefix="velero", namespace=NamespacesNames.ADP_NAMESPACE)
    return velero_pod.execute(command=shlex.split(f"./velero backup logs {backup_name}"))
