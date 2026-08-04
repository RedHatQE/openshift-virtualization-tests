from __future__ import annotations

from typing import TYPE_CHECKING

from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from utilities.constants import (
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    VELERO_BACKUP_HOOK_ANNOTATIONS,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

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


def assert_velero_backup_hooks_not_injected(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Assert virt-launcher has no Velero freeze/unfreeze hook annotations.

    Absence of these annotations means Velero will not execute filesystem
    freeze/unfreeze during backup.

    Args:
        vm: VirtualMachine whose virt-launcher pod is checked.
        admin_client: Privileged client used to access the virt-launcher pod.

    Raises:
        AssertionError: If any Velero hook annotations are found on the virt-launcher pod.
    """
    virt_launcher_pod = vm.vmi.get_virt_launcher_pod(privileged_client=admin_client)
    pod_annotations = virt_launcher_pod.instance.metadata.annotations or {}
    present_hook_annotations = [
        annotation_key for annotation_key in VELERO_BACKUP_HOOK_ANNOTATIONS if annotation_key in pod_annotations
    ]
    assert not present_hook_annotations, (
        f"VM {vm.name} virt-launcher pod has Velero hook annotations {present_hook_annotations} "
        f"but backup hooks should be disabled"
    )
