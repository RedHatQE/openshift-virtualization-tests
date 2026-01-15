import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.snapshots.constants import ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS
from utilities.constants import TIMEOUT_10MIN
from utilities.virt import running_vm


def expected_output_after_restore(snapshot_number):
    """
    Returns a string representing the list of files that should exist in the VM (sorted)
    after a restore snapshot was performed

    Args:
        snapshot_number (int): The snapshot number that was restored

    Returns:
        string: the list of files that should exist on the VM after restore operation was performed
    """
    files = []
    for idx in range(snapshot_number - 1):
        files.append(f"before-snap-{idx + 1}.txt")
        files.append(f"after-snap-{idx + 1}.txt")
    files.append(f"before-snap-{snapshot_number}.txt ")
    files.sort()
    return " ".join(files)


def fail_to_create_snapshot_no_permissions(snapshot_name, namespace, vm_name, client):
    with pytest.raises(
        ApiException,
        match=ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS,
    ):
        with VirtualMachineSnapshot(
            name=snapshot_name,
            namespace=namespace,
            vm_name=vm_name,
            client=client,
        ):
            return


def start_windows_vm_after_restore(vm_restore, windows_vm):
    vm_restore.wait_restore_done(timeout=TIMEOUT_10MIN)
    running_vm(vm=windows_vm)
