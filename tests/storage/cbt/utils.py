"""CBT backup utilities (backup success only)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_export import VirtualMachineExport
from timeout_sampler import TimeoutSampler

from tests.storage.cbt.constants import CBT_BACKUP_CONDITION_FAILED, CBT_DATA_DISK_SIZE
from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.constants.virt import CLOUD_INIT_DISK_NAME, DV_DISK
from utilities.storage import construct_datavolume_source_dict
from utilities.virt import VirtualMachineForTests

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine import VirtualMachine

LOGGER = logging.getLogger(__name__)

BYTES_PER_GIB = 1024**3


def cbt_pvc_size_with_headroom(source_disk_size: str, headroom_gib: int = 10) -> str:
    """Return a PVC size in Gi with headroom above the source disk capacity."""
    source_bytes = parse_quantity(quantity=source_disk_size)
    source_gib = int((source_bytes + BYTES_PER_GIB - 1) // BYTES_PER_GIB)
    return f"{source_gib + headroom_gib}Gi"


def cbt_pvc_size_for_vm(vm: VirtualMachine, headroom_gib: int = 10) -> str:
    """Return a backup/staging PVC size covering every VM dataVolumeTemplate plus headroom.

    Args:
        vm: VM whose dataVolumeTemplates sizes are summed.
        headroom_gib: Extra capacity in Gi added after rounding the disk total up.

    Returns:
        str: PVC size such as ``42Gi``.
    """
    templates = vm.instance.to_dict()["spec"]["dataVolumeTemplates"]
    total_bytes = sum(
        parse_quantity(quantity=template["spec"]["storage"]["resources"]["requests"]["storage"])
        for template in templates
    )
    total_gib = int((total_bytes + BYTES_PER_GIB - 1) // BYTES_PER_GIB)
    return cbt_pvc_size_with_headroom(source_disk_size=f"{total_gib}Gi", headroom_gib=headroom_gib)


def data_disk_name(index: int, unique_suffix: str) -> str:
    """Name of the Nth (1-indexed) additional blank data disk DataVolume/disk/volume for a CBT test VM."""
    return f"cbt-datadisk-{index}-{unique_suffix}"


def blank_data_disk_template(name: str, namespace: str, storage_class_name: str) -> dict[str, Any]:
    """Build a blank DataVolume dict for VM dataVolumeTemplates.

    Args:
        name: DataVolume name.
        namespace: Namespace used to construct the DataVolume, then stripped from the dict.
        storage_class_name: Storage class for the blank PVC.

    Returns:
        dict[str, Any]: DataVolume resource dict without namespace, for dataVolumeTemplates.
    """
    data_volume = DataVolume(
        name=name,
        namespace=namespace,
        source_dict=construct_datavolume_source_dict(source="blank"),
        size=CBT_DATA_DISK_SIZE,
        storage_class=storage_class_name,
        api_name="storage",
    )
    data_volume.to_dict()
    del data_volume.res["metadata"]["namespace"]
    return data_volume.res


class CbtVmWithDataDisks(VirtualMachineForTests):
    """CBT test VM that injects blank data disks at creation time to avoid post-create PATCH calls."""

    def __init__(
        self,
        data_disk_storage_class_name: str,
        data_disk_count: int,
        unique_suffix: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.data_disk_storage_class_name = data_disk_storage_class_name
        self.data_disk_count = data_disk_count
        self.unique_suffix = unique_suffix

    def to_dict(self) -> None:
        """Build the VM resource dict and add blank data-disk entries to it.

        Side effects:
            Mutates ``self.res`` with dataVolumeTemplates, disks, and volumes for each blank data disk.

        Note:
            Do not call more than once. Each call appends the blank disks to the resource dict,
            so a second call will result in duplicate disks.
        """
        super().to_dict()
        template_spec = self.res["spec"]["template"]["spec"]
        disks = template_spec["domain"]["devices"]["disks"]
        volumes = template_spec["volumes"]
        dv_templates = self.res["spec"]["dataVolumeTemplates"]

        for disk_index in range(1, self.data_disk_count + 1):
            volume_name = data_disk_name(index=disk_index, unique_suffix=self.unique_suffix)
            dv_templates.append(
                blank_data_disk_template(
                    name=volume_name,
                    namespace=self.namespace,
                    storage_class_name=self.data_disk_storage_class_name,
                )
            )
            disks.append({"disk": {"bus": self.disk_type}, "name": volume_name})
            volumes.append({"name": volume_name, "dataVolume": {"name": volume_name}})


def guest_volume_target(vm: VirtualMachine, volume_name: str) -> str | None:
    """Guest device name (for example ``vdc``) for a volume, from VMI volumeStatus.

    ``volumeStatus`` is absent from the VMI status until the volumes report in, so a missing
    value is treated as no volumes found yet, rather than an error, to keep polling.

    Args:
        vm: Running VM to inspect.
        volume_name: VM volume name to resolve.

    Returns:
        str | None: The guest device target, or ``None`` if the volume has no target yet.
    """
    for volume_status in vm.vmi.instance.status.volumeStatus or []:
        if volume_status.get("name") == volume_name:
            return volume_status.get("target")
    return None


def _wait_for_guest_volume_target(vm: VirtualMachine, volume_name: str) -> None:
    """Wait until the volume reports a guest device name.

    Args:
        vm: Running VM to inspect.
        volume_name: VM volume name to wait for.

    Side effects:
        Polls the VMI until the volume reports a guest device name.

    Raises:
        TimeoutExpiredError: If the volume never reports a guest device name within the timeout.
    """
    LOGGER.info(f"Waiting for guest device of volume {volume_name} on VM {vm.name}")
    for target in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=guest_volume_target,
        vm=vm,
        volume_name=volume_name,
    ):
        if target:
            return


def guest_device_path_for_volume(vm: VirtualMachine, volume_name: str) -> str:
    """Guest ``/dev`` path for a named volume, taken from VMI ``volumeStatus.target``.

    Args:
        vm: Running VM to inspect.
        volume_name: VM volume name to resolve.

    Returns:
        str: The guest ``/dev`` path for the volume (for example ``/dev/vdc``).

    Side effects:
        Polls the VMI until the volume reports a guest device name.

    Raises:
        TimeoutExpiredError: If the volume never reports a guest device name within the timeout.
    """
    _wait_for_guest_volume_target(vm=vm, volume_name=volume_name)
    return f"/dev/{guest_volume_target(vm=vm, volume_name=volume_name)}"


def attached_data_disk_names(vm: VirtualMachine) -> list[str]:
    """Names of additional data disk volumes attached to a VM.

    Args:
        vm: VM to inspect.

    Returns:
        list[str]: Sorted names of attached data disk volumes, excluding the boot disk and cloud-init disk.
    """
    volumes = vm.instance.to_dict()["spec"]["template"]["spec"]["volumes"]
    excluded_names = {DV_DISK, CLOUD_INIT_DISK_NAME}
    return sorted(volume["name"] for volume in volumes if volume["name"] not in excluded_names)


def incremental_test_data(index: int) -> str:
    """Content written to the VM before the Nth (1-indexed) incremental backup in a backup chain."""
    return f"cbt-incremental-{index}-backup-test-data"


def incremental_test_data_file(index: int) -> str:
    """Guest file path written before the Nth (1-indexed) incremental backup in a backup chain."""
    return f"/tmp/cbt-incremental-{index}-test-data.txt"


def assert_backup_status_includes_volumes(
    backup_name: str,
    backup_status: Any,
    expected_volume_names: list[str],
    expected_backup_type: str | None = None,
) -> None:
    """Assert a backup status includes the expected volumes (and optional type)."""
    included_volumes = backup_status["includedVolumes"]
    actual_volume_names = [volume["volumeName"] for volume in included_volumes]
    assert sorted(actual_volume_names) == sorted(expected_volume_names), (
        f"Backup {backup_name} included volumes {actual_volume_names}, "
        f"expected {expected_volume_names}: {included_volumes}"
    )
    if expected_backup_type is not None:
        assert backup_status["type"] == expected_backup_type, (
            f"Backup {backup_name} type is {backup_status['type']!r}, expected {expected_backup_type!r}"
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


def deploy_cbt_pull_backup(
    name: str,
    namespace: str,
    client: DynamicClient,
    token_secret_name: str,
    pvc_name: str,
    source: dict[str, str],
    *,
    force_full_backup: bool,
) -> VirtualMachineBackup:
    """Create and deploy a pull-mode VirtualMachineBackup.

    Args:
        name: Backup resource name.
        namespace: Namespace for the backup.
        client: Client used to create the backup.
        token_secret_name: Name of the pull-mode token secret.
        pvc_name: Staging PVC name.
        source: Backup tracker source reference.
        force_full_backup: Whether this backup is a full backup.

    Returns:
        VirtualMachineBackup: Deployed pull-mode backup (not yet waited for export ready).
    """
    backup = VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name=name,
        namespace=namespace,
        client=client,
        token_secret_ref=token_secret_name,
        pvc_name=pvc_name,
        force_full_backup=force_full_backup,
        source=source,
    )
    backup.deploy()
    return backup
