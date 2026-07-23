"""CBT backup utilities (backup success only)."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.virtual_machine_export import VirtualMachineExport
from timeout_sampler import TimeoutSampler

from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine import VirtualMachine
    from ocp_resources.virtual_machine_backup import VirtualMachineBackup

LOGGER = logging.getLogger(__name__)

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_INCREMENTAL_TEST_DATA: str = "cbt-incremental-backup-test-data"
CBT_BOOT_DISK_TEST_DATA_FILE = "/tmp/cbt-test-data.txt"
CBT_INCREMENTAL_TEST_DATA_FILE = "/tmp/cbt-incremental-test-data.txt"
CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}


def cbt_pvc_size_with_headroom(source_disk_size: str, headroom_gib: int = 10) -> str:
    """Return a PVC size with headroom above the source disk capacity."""
    source_gib = parse_quantity(source_disk_size) // (1024**3)
    return f"{source_gib + headroom_gib}Gi"


def cbt_resource_id(name: str) -> str:
    """Return a short stable identifier for CBT resource names."""
    return hashlib.sha256(name.encode()).hexdigest()[:10]


def assert_backup_includes_volumes(
    *,
    backup: VirtualMachineBackup,
    expected_volume_count: int,
    expected_backup_type: str | None = None,
) -> None:
    """Assert a ready backup includes the expected volumes (and optional type)."""
    backup_status = backup.instance.status
    included_volumes = backup_status["includedVolumes"]
    assert len(included_volumes) == expected_volume_count, (
        f"Backup {backup.name} included {len(included_volumes)} volumes, "
        f"expected {expected_volume_count}: {included_volumes}"
    )
    if expected_backup_type is not None:
        assert backup_status["type"] == expected_backup_type, (
            f"Backup {backup.name} type is {backup_status['type']!r}, expected {expected_backup_type!r}"
        )


def wait_for_vm_cbt_enabled(vm: VirtualMachine) -> None:
    """Wait until changed block tracking is Enabled on the VM."""
    LOGGER.info(f"Waiting for CBT Enabled on VM {vm.name}")
    for cbt_state in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: vm.instance.status.get("changedBlockTracking", {}).get("state"),
    ):
        if cbt_state == "Enabled":
            return


def wait_for_pull_backup_export_deleted(*, name: str, namespace: str, client: DynamicClient) -> None:
    """Wait until the VirtualMachineExport owned by a pull-mode backup is gone."""
    export = VirtualMachineExport(name=name, namespace=namespace, client=client)
    LOGGER.info(f"Waiting for VirtualMachineExport {namespace}/{name} to be deleted")
    for export_deleted in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: not export.exists,
    ):
        if export_deleted:
            return
