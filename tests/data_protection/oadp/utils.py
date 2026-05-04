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


def write_file_windows_vm_for_oadp(vm: VirtualMachineForTests) -> None:
    """
    Write test data to marker file on Windows VM for OADP backup verification.

    Writes TEXT_TO_TEST constant to FILE_PATH_FOR_WINDOWS_BACKUP on the Windows VM
    using PowerShell over SSH with retry logic.

    Args:
        vm: Windows VirtualMachine instance with SSH connectivity

    Raises:
        TimeoutExpiredError: If SSH command fails within 2 minute retry timeout
    """
    write_file_windows_vm(vm=vm, file_path=FILE_PATH_FOR_WINDOWS_BACKUP, content=TEXT_TO_TEST)
