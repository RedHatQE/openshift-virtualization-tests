from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
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


class VirtualMachineRestoreWithPolicy(VirtualMachineRestore):
    """VirtualMachineRestore with custom volumeRestorePolicy."""

    def __init__(self, volume_restore_policy: str, **kwargs):
        """
        Initialize VirtualMachineRestore with volumeRestorePolicy.

        Args:
            volume_restore_policy: Policy for volume restoration (e.g., "PrefixTargetName")
            **kwargs: Arguments for VirtualMachineRestore parent class
        """
        super().__init__(**kwargs)
        self.volume_restore_policy = volume_restore_policy

    def to_dict(self):
        super().to_dict()
        self.res["spec"]["volumeRestorePolicy"] = self.volume_restore_policy


@contextmanager
def vm_restore_with_prefix_policy(
    name: str,
    namespace: str,
    vm_name: str,
    snapshot_name: str,
    client: DynamicClient,
    prefix_policy: str,
    dry_run: bool = False,
    **kwargs: Any,
) -> Generator[VirtualMachineRestore]:
    """
    Creates VirtualMachineRestore with volumeRestorePolicy: PrefixTargetName.

    This allows restoring snapshots to new VMs without overwriting original PVCs.
    The restored PVCs will be prefixed with the target VM name.

    Args:
        name: Restore object name
        namespace: Kubernetes namespace
        client: Kubernetes client (must be admin)
        vm_name: Target VM name (will be created/updated)
        snapshot_name: VirtualMachineSnapshot name to restore from
        prefix_policy: VolumeRestorePolicy to use
        **kwargs: Additional arguments for VirtualMachineRestore

    Yields:
        VirtualMachineRestore: Configured restore object
    """
    with VirtualMachineRestoreWithPolicy(
        name=name,
        namespace=namespace,
        vm_name=vm_name,
        snapshot_name=snapshot_name,
        client=client,
        dry_run=dry_run,
        volume_restore_policy=prefix_policy,
        **kwargs,
    ) as restore:
        yield restore


def assert_restored_dv_pvc_predictable_names(
    restored_vm_name: str,
    source_volume_name: str,
    restored_dv_name: str,
    restored_pvc_name: str,
    volume_restore_policy: str,
) -> None:
    """Verifies restored DV/PVC names follow the PrefixTargetName policy.

    Args:
        restored_vm_name: Name of the target (restored) VM.
        source_volume_name: Volume name from the source VM spec.
        restored_dv_name: Actual DataVolume name from restore status.
        restored_pvc_name: Actual PVC name from restore status.
        volume_restore_policy: Policy value from the restore spec.
    """
    expected_name = f"{restored_vm_name}-{source_volume_name}"[:63]

    assert volume_restore_policy == "PrefixTargetName", (
        f"volumeRestorePolicy is '{volume_restore_policy}', expected 'PrefixTargetName'"
    )
    assert restored_dv_name == expected_name, f"Restored DV name is '{restored_dv_name}', expected '{expected_name}'"
    assert restored_pvc_name == expected_name, f"Restored PVC name is '{restored_pvc_name}', expected '{expected_name}'"
