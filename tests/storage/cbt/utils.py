"""CBT backup utilities (backup success only)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.virtual_machine_export import VirtualMachineExport
from timeout_sampler import TimeoutSampler

from tests.storage.cbt.constants import CBT_BACKUP_CONDITION_FAILED
from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine import VirtualMachine
    from ocp_resources.virtual_machine_backup import VirtualMachineBackup

LOGGER = logging.getLogger(__name__)

BYTES_PER_GIB = 1024**3


def cbt_pvc_size_with_headroom(source_disk_size: str, headroom_gib: int = 10) -> str:
    """Return a PVC size in Gi with headroom above the source disk capacity."""
    source_bytes = parse_quantity(quantity=source_disk_size)
    source_gib = int((source_bytes + BYTES_PER_GIB - 1) // BYTES_PER_GIB)
    return f"{source_gib + headroom_gib}Gi"


def assert_backup_includes_volumes(
    backup: VirtualMachineBackup,
    expected_volume_names: list[str],
    expected_backup_type: str | None = None,
) -> None:
    """Assert a ready backup includes the expected volumes (and optional type)."""
    backup_status = backup.instance.status
    included_volumes = backup_status["includedVolumes"]
    actual_volume_names = [volume["volumeName"] for volume in included_volumes]
    assert sorted(actual_volume_names) == sorted(expected_volume_names), (
        f"Backup {backup.name} included volumes {actual_volume_names}, "
        f"expected {expected_volume_names}: {included_volumes}"
    )
    if expected_backup_type is not None:
        assert backup_status["type"] == expected_backup_type, (
            f"Backup {backup.name} type is {backup_status['type']!r}, expected {expected_backup_type!r}"
        )


def wait_for_vm_cbt_enabled(vm: VirtualMachine) -> None:
    """Wait until changed block tracking is Enabled on the VM.

    Args:
        vm: VM to poll for CBT status.

    Side effects:
        Polls the OpenShift API until the VM reports changedBlockTracking.state == "Enabled".
    """
    LOGGER.info(f"Waiting for CBT Enabled on VM {vm.name}")
    for cbt_state in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: vm.instance.status.get("changedBlockTracking", {}).get("state"),
    ):
        if cbt_state == "Enabled":
            return


def wait_for_push_backup_complete(backup: VirtualMachineBackup) -> None:
    """Wait until a push-mode backup completes successfully.

    Args:
        backup: Push-mode backup resource to poll.

    Side effects:
        Polls the OpenShift API until the backup reports Complete=True.

    Raises:
        ConditionError: If the backup reports Failed=True before completing.
    """
    LOGGER.info(f"Waiting for push-mode backup {backup.name} to complete")
    backup.wait_for_condition(
        condition="Complete",
        status=backup.Condition.Status.TRUE,
        timeout=TIMEOUT_10MIN,
        sleep_time=TIMEOUT_5SEC,
        stop_condition=CBT_BACKUP_CONDITION_FAILED,
        stop_status=backup.Condition.Status.TRUE,
    )


def wait_for_pull_backup_export_ready(backup: VirtualMachineBackup) -> None:
    """Wait until a pull-mode backup export is ready for collection.

    Args:
        backup: Pull-mode backup resource to poll.

    Side effects:
        Polls the OpenShift API until the backup reports Progressing=True with reason
        ExportReady (there is no ExportReady condition type).

    Raises:
        ConditionError: If the backup reports Failed=True before the export becomes ready.
    """
    LOGGER.info(f"Waiting for pull-mode backup {backup.name} export to become ready")
    backup.wait_for_condition(
        condition="Progressing",
        status=backup.Condition.Status.TRUE,
        reason="ExportReady",
        timeout=TIMEOUT_10MIN,
        sleep_time=TIMEOUT_5SEC,
        stop_condition=CBT_BACKUP_CONDITION_FAILED,
        stop_status=backup.Condition.Status.TRUE,
    )


def wait_for_pull_backup_export_deleted(name: str, namespace: str, client: DynamicClient) -> None:
    """Wait until the VirtualMachineExport owned by a pull-mode backup is gone.

    Args:
        name: Name of the VirtualMachineExport (matches the owning pull-mode backup name).
        namespace: Namespace of the VirtualMachineExport.
        client: Client used to poll the VirtualMachineExport.

    Side effects:
        Polls the OpenShift API until the VirtualMachineExport is deleted.
    """
    export = VirtualMachineExport(name=name, namespace=namespace, client=client)
    LOGGER.info(f"Waiting for VirtualMachineExport {namespace}/{name} to be deleted")
    export.wait_deleted(timeout=TIMEOUT_10MIN)
