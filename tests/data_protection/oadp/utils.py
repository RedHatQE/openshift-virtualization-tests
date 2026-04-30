from __future__ import annotations

from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from utilities.constants import (
    TEXT_TO_TEST,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
)
from utilities.storage import write_file_windows_vm
from utilities.virt import VirtualMachineForTests

FILE_PATH_FOR_WINDOWS_BACKUP = "C:/oadp_file_before_backup.txt"

OADP_DPA_NAME = "dpa"
# Temporary workaround: custom Velero image with CSI snapshot polling fixes
# TODO: Remove once https://github.com/velero-io/velero/issues/9601 is merged into OADP 1.6
OADP_VELERO_IMAGE_FQIN_OVERRIDE = "quay.io/sseago/velero:csi-quick-poll"


def wait_for_restored_dv(dv: DataVolume) -> None:
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


def write_file_windows_vm_for_oadp(vm: VirtualMachineForTests) -> None:
    """Write test data to marker file on Windows VM for OADP backup verification."""
    write_file_windows_vm(vm=vm, file_path=FILE_PATH_FOR_WINDOWS_BACKUP, content=TEXT_TO_TEST)
