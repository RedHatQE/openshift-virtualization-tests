"""CBT backup utilities (backup success only)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_export import VirtualMachineExport
from timeout_sampler import TimeoutSampler

from tests.storage.cbt.constants import (
    CBT_BACKUP_CONDITION_FAILED,
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_DATA_DISK_SIZE,
    CBT_DATA_DISK_TEST_DATA,
    CBT_ENABLED_LABEL,
    CBT_TEST_DATA,
)
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL
from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.constants.virt import CLOUD_INIT_DISK_NAME, DV_DISK
from utilities.storage import (
    construct_datavolume_source_dict,
    data_volume_template_with_source_ref_dict,
    write_file_via_ssh,
)
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource

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


@contextmanager
def cbt_enabled_vm(
    name: str,
    namespace: str,
    client: DynamicClient,
    data_source: DataSource,
    storage_class: str,
    unique_suffix: str,
    data_disk_count: int = 0,
) -> Generator[VirtualMachineForTests]:
    """Create a running CBT-enabled VM with test data written to every disk.

    Args:
        name: VM name.
        namespace: Namespace for the VM and any additional data disks.
        client: Client used to create the VM.
        data_source: Golden-image DataSource for the boot disk.
        storage_class: Storage class for the boot disk and additional data disks.
        unique_suffix: Suffix used in additional data disk names.
        data_disk_count: Number of blank data disks to attach before first start.

    Yields:
        VirtualMachineForTests: Running VM with CBT enabled and test data written.

    Side effects:
        Creates the VM (and optional blank data disks), starts it, waits for CBT
        Enabled, and writes test data to the boot disk and every data disk.
    """
    with CbtVmWithDataDisks(
        name=name,
        namespace=namespace,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=client, name=RHEL9_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class,
        ),
        os_flavor=OS_FLAVOR_RHEL,
        label=CBT_ENABLED_LABEL,
        data_disk_storage_class_name=storage_class,
        data_disk_count=data_disk_count,
        unique_suffix=unique_suffix,
    ) as vm:
        running_vm(vm=vm)
        wait_for_vm_cbt_enabled(vm=vm)
        write_file_via_ssh(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE, content=CBT_TEST_DATA)
        for disk_index in range(1, data_disk_count + 1):
            volume_name = data_disk_name(index=disk_index, unique_suffix=unique_suffix)
            write_file_via_ssh(
                vm=vm,
                filename=guest_device_path_for_volume(vm=vm, volume_name=volume_name),
                content=CBT_DATA_DISK_TEST_DATA,
                use_sudo=True,
            )
        yield vm


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


def _wait_for_guest_volume_target(vm: VirtualMachine, volume_name: str) -> str:
    """Wait until the volume reports a guest device name.

    Args:
        vm: Running VM to inspect.
        volume_name: VM volume name to wait for.

    Returns:
        str: The guest device target sampled from VMI ``volumeStatus``.

    Side effects:
        Polls the VMI until the volume reports a guest device name.

    Raises:
        TimeoutExpiredError: If the volume never reports a guest device name within the timeout.
    """
    LOGGER.info(f"Waiting for guest device of volume {volume_name} on VM {vm.name}")
    return next(
        target
        for target in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=TIMEOUT_5SEC,
            func=guest_volume_target,
            vm=vm,
            volume_name=volume_name,
        )
        if target
    )


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
    target = _wait_for_guest_volume_target(vm=vm, volume_name=volume_name)
    return f"/dev/{target}"


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
    backup_status: dict[str, Any],
    expected_volume_names: list[str],
    expected_backup_type: str | None = None,
) -> None:
    """Assert a previously captured backup status includes the expected volumes.

    Inspects ``includedVolumes`` and, when requested, the optional ``type`` field.
    Does not read a live backup resource.

    Args:
        backup_name: Backup resource name used in assertion messages.
        backup_status: Previously captured backup status mapping, not a live resource.
        expected_volume_names: Volume names that must appear in ``includedVolumes``.
        expected_backup_type: Expected ``status.type`` value. When omitted, type is not checked.
    """
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


def cbt_source_ref(resource: VirtualMachine | VirtualMachineBackupTracker) -> dict[str, str]:
    """TypedLocalObjectReference dict for a VirtualMachine or VirtualMachineBackupTracker."""
    return {
        "apiGroup": resource.api_group,
        "kind": resource.kind,
        "name": resource.name,
    }


@contextmanager
def cbt_backup_tracker(
    namespace: str,
    client: DynamicClient,
    vm: VirtualMachine,
) -> Generator[VirtualMachineBackupTracker]:
    """Create a VirtualMachineBackupTracker for a VM.

    Args:
        namespace: Namespace for the tracker.
        client: Client used to create the tracker.
        vm: VM the tracker watches.

    Yields:
        VirtualMachineBackupTracker: Tracker for the VM.
    """
    with VirtualMachineBackupTracker(
        name=f"{vm.name}-tracker",
        namespace=namespace,
        client=client,
        source=cbt_source_ref(resource=vm),
    ) as tracker:
        yield tracker


def cbt_backup_pvc(
    name: str,
    namespace: str,
    client: DynamicClient,
    vm: VirtualMachine,
    storage_class: str,
) -> PersistentVolumeClaim:
    """Build an RWO filesystem PVC sized for a CBT VM's disks.

    Does not create the resource. Callers must enter it as a context manager.

    Args:
        name: PVC name.
        namespace: Namespace for the PVC.
        client: Client used to create the PVC.
        vm: VM whose dataVolumeTemplates determine PVC size.
        storage_class: Storage class for the PVC.

    Returns:
        PersistentVolumeClaim: Undeployed RWO filesystem PVC.
    """
    return PersistentVolumeClaim(
        name=name,
        namespace=namespace,
        client=client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_for_vm(vm=vm),
        storage_class=storage_class,
        volume_mode=PersistentVolumeClaim.VolumeMode.FILE,
    )


def cbt_push_backup(
    name: str,
    namespace: str,
    client: DynamicClient,
    pvc_name: str,
    source: dict[str, str],
    force_full_backup: bool,
) -> VirtualMachineBackup:
    """Build a push-mode VirtualMachineBackup for use as a context manager.

    Does not create the resource. Callers must enter it (for example via ExitStack)
    so deploy and cleanup stay with the context manager.

    Args:
        name: Backup resource name.
        namespace: Namespace for the backup.
        client: Client used to create the backup.
        pvc_name: Push-mode backup PVC name.
        source: Backup tracker source reference.
        force_full_backup: Whether this backup is a full backup.

    Returns:
        VirtualMachineBackup: Undeployed push-mode backup.
    """
    return VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name=name,
        namespace=namespace,
        client=client,
        pvc_name=pvc_name,
        force_full_backup=force_full_backup,
        source=source,
    )


def deploy_cbt_pull_backup(
    name: str,
    namespace: str,
    client: DynamicClient,
    token_secret_name: str,
    pvc_name: str,
    source: dict[str, str],
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


def delete_cbt_pull_backup_and_wait_for_export(backup: VirtualMachineBackup) -> None:
    """Delete a pull-mode backup and wait until its VirtualMachineExport is gone.

    Args:
        backup: Deployed pull-mode backup to delete.

    Side effects:
        Deletes the backup and polls until the matching VirtualMachineExport is
        deleted so the staging PVC can be reused.
    """
    backup_name = backup.name
    namespace = backup.namespace
    client = backup.client
    backup.delete(wait=True)
    wait_for_pull_backup_export_deleted(name=backup_name, namespace=namespace, client=client)


def live_migrate_cbt_vm(vm: VirtualMachineForTests, client: DynamicClient) -> None:
    """Live-migrate a CBT VM and wait until CBT is Enabled again.

    Args:
        vm: Running CBT-enabled VM to migrate.
        client: Admin client used to create the migration.

    Side effects:
        Live-migrates the VM, verifies SSH, and polls until CBT is Enabled.
    """
    LOGGER.info(f"Live-migrating VM {vm.name} before incremental backup")
    migrate_vm_and_verify(vm=vm, client=client, check_ssh_connectivity=True)
    wait_for_vm_cbt_enabled(vm=vm)
