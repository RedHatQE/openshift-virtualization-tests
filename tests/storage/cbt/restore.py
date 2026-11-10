"""CBT push-mode full backup restore.

OpenShift Virtualization has no restore API for changed-block-tracking backups.
These helpers rebuild the boot disk from a push-mode full backup, start the VM,
and let the test confirm the guest data survived.

The backup is the only source for the VM name, the volume, and the disk bytes.
The caller deletes the source VM before restore so that name can be reused.
"""

from __future__ import annotations

import json
import logging
import shlex
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError

from tests.storage.cbt.constants import (
    CBT_BACKUP_DIR,
    CBT_BACKUP_PVC_VOLUME_NAME,
    CBT_BACKUP_TYPE_FULL,
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_ENABLED_LABEL,
    CBT_FILESYSTEM_RESTORE_HEADROOM_GIB,
    CBT_INSTANCE_TYPE_NAME,
    CBT_OS_FLAVOR,
    CBT_PREFERENCE_NAME,
    CBT_TARGET_DEVICE_PATH,
    CBT_TARGET_MOUNT_PATH,
    CBT_TARGET_VOLUME_NAME,
    CBT_TEST_DATA,
)
from tests.storage.cbt.utils import cbt_pvc_size_with_headroom
from utilities.constants.networking import POD_CONTAINER_SPEC
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_30MIN
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from collections.abc import Generator

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine_backup import VirtualMachineBackup

LOGGER = logging.getLogger(__name__)

# restricted-v2 assigns the namespace UID and fsGroup. Leave runAsUser, fsGroup,
# and hostUsers unset so admission succeeds and the container can call setgroups.
CBT_RUNNER_POD_SECURITY_CONTEXT: dict[str, Any] = {
    "seccompProfile": {"type": "RuntimeDefault"},
    "runAsNonRoot": True,
}


@dataclass(frozen=True)
class CbtVolumeRestoreSpec:
    """Volume from the backup and the PVC that will hold the restored raw disk."""

    volume_name: str
    size: str
    storage_class: str
    volume_mode: str
    access_mode: str


@dataclass(frozen=True)
class _RestoredDiskStorage:
    """Storage class from the backup PVC, and the volume mode and access mode of that class.

    The backup PVC is a filesystem volume so it can hold qcow2 files. The restored disk uses
    the storage class profile, which is how the source disk was provisioned.
    """

    storage_class: str
    volume_mode: str
    access_mode: str


def assert_restored_cbt_vm_data(vm: VirtualMachineForTests) -> None:
    """Assert a restored VM still has the boot-disk file written before the backup.

    Args:
        vm: Running restored VM.

    Raises:
        AssertionError: When the guest file is missing or has different content.
    """
    output = _read_linux_guest_file(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE)
    assert output.strip() == CBT_TEST_DATA, (
        f"VM {vm.name} file {CBT_BOOT_DISK_TEST_DATA_FILE} is {output.strip()!r}, expected {CBT_TEST_DATA!r}"
    )


@contextmanager
def restored_cbt_vm_from_push_backup(
    *,
    backups: list[VirtualMachineBackup],
    backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
) -> Generator[VirtualMachineForTests]:
    """Rebuild the boot disk from the full push backup and start a VM with the backup's VM name.

    The caller deletes the source VM first. This function reads the backup, the backup PVC's
    storage class, and that class's storage profile.

    Args:
        backups: Completed push backups. A full-backup restore contains exactly one backup.
        backup_pvc_name: PVC that holds the qcow2 backup.
        namespace: Namespace for the restored VM and target PVC.
        client: Client used to create the restored VM, PVC, and restore pod.

    Yields:
        VirtualMachineForTests: Running restored VM.

    Side effects:
        Writes the restored boot disk, and deletes the restored VM and target PVC on exit.
    """
    backup = _single_full_backup(backups=backups)
    vm_name = _backed_up_vm_name(backup=backup, namespace=namespace, client=client)
    volume_name = _full_backup_volume_name(backup=backup)
    backup_storage = _restored_disk_storage(
        backup_pvc_name=backup_pvc_name,
        namespace=namespace,
        client=client,
    )
    qcow2_file, virtual_size_bytes = _inspect_backup_qcow2(
        vm_name=vm_name,
        volume_name=volume_name,
        backup_pvc_name=backup_pvc_name,
        backup=backup,
        namespace=namespace,
        client=client,
    )
    volume_spec = CbtVolumeRestoreSpec(
        volume_name=volume_name,
        size=_target_pvc_size(virtual_size_bytes=virtual_size_bytes, volume_mode=backup_storage.volume_mode),
        storage_class=backup_storage.storage_class,
        volume_mode=backup_storage.volume_mode,
        access_mode=backup_storage.access_mode,
    )
    target_pvc: PersistentVolumeClaim | None = None
    restored_vm: VirtualMachineForTests | None = None
    try:
        target_pvc = _deploy_target_pvc(
            vm_name=vm_name,
            volume_spec=volume_spec,
            namespace=namespace,
            client=client,
        )
        _restore_push_volume(
            vm_name=vm_name,
            volume_spec=volume_spec,
            target_pvc=target_pvc,
            backup_pvc_name=backup_pvc_name,
            qcow2_file=qcow2_file,
            namespace=namespace,
            client=client,
        )
        restored_vm = _deploy_restored_vm(
            vm_name=vm_name,
            target_pvc=target_pvc,
            namespace=namespace,
            client=client,
        )
        LOGGER.info(f"Starting restored VM {vm_name}")
        running_vm(vm=restored_vm, ssh_timeout=TIMEOUT_5MIN)
        yield restored_vm
    finally:
        if restored_vm is not None and restored_vm.exists:
            restored_vm.clean_up(wait=True)
        if target_pvc is not None and target_pvc.exists:
            target_pvc.clean_up(wait=True)


def _single_full_backup(*, backups: list[VirtualMachineBackup]) -> VirtualMachineBackup:
    """Return the one backup a full restore can apply."""
    if len(backups) != 1:
        backup_names = [backup.name for backup in backups]
        raise RuntimeError(f"Push full restore expects one backup, got {len(backups)}: {backup_names}")
    return backups[0]


def _backed_up_vm_name(*, backup: VirtualMachineBackup, namespace: str, client: DynamicClient) -> str:
    """Return the VM name recorded on the backup or its tracker."""
    source = backup.instance.to_dict()["spec"]["source"]
    source_name = str(source["name"])
    if source["kind"] != VirtualMachineBackupTracker.kind:
        return source_name
    tracker = VirtualMachineBackupTracker(name=source_name, namespace=namespace, client=client)
    return str(tracker.instance.to_dict()["spec"]["source"]["name"])


def _full_backup_volume_name(*, backup: VirtualMachineBackup) -> str:
    """Return the single volume recorded on a full backup.

    Backup type is ``status.type``. ``includedVolumes`` entries carry only ``volumeName``.
    """
    status = backup.instance.to_dict()["status"]
    backup_type = status["type"]
    if backup_type != CBT_BACKUP_TYPE_FULL:
        raise RuntimeError(f"Backup {backup.name} type is {backup_type!r}, expected {CBT_BACKUP_TYPE_FULL!r}")
    volume_names = [str(volume["volumeName"]) for volume in status["includedVolumes"]]
    if len(volume_names) != 1:
        raise RuntimeError(f"Backup {backup.name} full restore expects one volume, got {volume_names}")
    return volume_names[0]


def _restored_disk_storage(*, backup_pvc_name: str, namespace: str, client: DynamicClient) -> _RestoredDiskStorage:
    """Return the storage class of the backup PVC and that class's disk claim shape."""
    pvc = PersistentVolumeClaim(name=backup_pvc_name, namespace=namespace, client=client)
    storage_class = pvc.instance.to_dict()["spec"]["storageClassName"]
    claim = StorageProfile(name=storage_class, client=client).instance.to_dict()["status"]["claimPropertySets"][0]
    return _RestoredDiskStorage(
        storage_class=storage_class,
        volume_mode=claim["volumeMode"],
        access_mode=claim["accessModes"][0],
    )


def _target_file(volume_mode: str) -> str:
    """Return the in-pod path of the disk being restored."""
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return CBT_TARGET_DEVICE_PATH
    return f"{CBT_TARGET_MOUNT_PATH}/disk.img"


def _target_pod_volumes(
    *,
    pvc_name: str,
    volume_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return volume mounts, devices, and volumes for the restore target PVC."""
    volumes = [{"name": CBT_TARGET_VOLUME_NAME, "persistentVolumeClaim": {"claimName": pvc_name}}]
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return [], [{"name": CBT_TARGET_VOLUME_NAME, "devicePath": CBT_TARGET_DEVICE_PATH}], volumes
    return [{"name": CBT_TARGET_VOLUME_NAME, "mountPath": CBT_TARGET_MOUNT_PATH}], [], volumes


def _inspect_backup_qcow2(
    *,
    vm_name: str,
    volume_name: str,
    backup_pvc_name: str,
    backup: VirtualMachineBackup,
    namespace: str,
    client: DynamicClient,
) -> tuple[str, int]:
    """Return the full-backup qcow2 path and its virtual size in bytes."""
    checkpoint_name = str(backup.instance.to_dict()["status"]["checkpointName"])
    backup_mounts, backup_volumes = _backup_pod_volumes(backup_pvc_name=backup_pvc_name)
    LOGGER.info(f"Reading backup qcow2 for volume {volume_name} of VM {vm_name}")
    with _push_restore_pod(
        pod_name=f"cbt-info-{vm_name}",
        namespace=namespace,
        client=client,
        volume_mounts=backup_mounts,
        volume_devices=[],
        volumes=backup_volumes,
    ) as inspect_pod:
        qcow2_file = _select_volume_qcow2(
            qcow2_files=_list_qcow2_files(pod=inspect_pod),
            vm_name=vm_name,
            backup_name=backup.name,
            checkpoint_name=checkpoint_name,
            volume_name=volume_name,
        )
        return qcow2_file, _qcow2_virtual_size_bytes(pod=inspect_pod, qcow2_file=qcow2_file)


def _restore_push_volume(
    *,
    vm_name: str,
    volume_spec: CbtVolumeRestoreSpec,
    target_pvc: PersistentVolumeClaim,
    backup_pvc_name: str,
    qcow2_file: str,
    namespace: str,
    client: DynamicClient,
) -> None:
    """Write the full push-mode qcow2 onto the target PVC."""
    target_file = _target_file(volume_mode=volume_spec.volume_mode)
    target_mounts, target_devices, target_volumes = _target_pod_volumes(
        pvc_name=target_pvc.name,
        volume_mode=volume_spec.volume_mode,
    )
    backup_mounts, backup_volumes = _backup_pod_volumes(backup_pvc_name=backup_pvc_name)
    LOGGER.info(f"Restoring push volume {volume_spec.volume_name} for VM {vm_name}")
    with _push_restore_pod(
        pod_name=f"cbt-rstr-{vm_name}",
        namespace=namespace,
        client=client,
        volume_mounts=[*target_mounts, *backup_mounts],
        volume_devices=target_devices,
        volumes=[*target_volumes, *backup_volumes],
    ) as restore_pod:
        LOGGER.info(f"Converting {qcow2_file} onto {target_file}")
        restore_pod.execute(
            command=["qemu-img", "convert", "-f", "qcow2", "-O", "raw", qcow2_file, target_file],
            timeout=TIMEOUT_30MIN,
        )
        LOGGER.info(f"Comparing {qcow2_file} with {target_file}")
        restore_pod.execute(
            command=["qemu-img", "compare", "-f", "qcow2", "-F", "raw", qcow2_file, target_file],
            timeout=TIMEOUT_30MIN,
        )


def _backup_pod_volumes(*, backup_pvc_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the mount and volume for the backup PVC."""
    return (
        [{"name": CBT_BACKUP_PVC_VOLUME_NAME, "mountPath": CBT_BACKUP_DIR, "readOnly": True}],
        [{"name": CBT_BACKUP_PVC_VOLUME_NAME, "persistentVolumeClaim": {"claimName": backup_pvc_name}}],
    )


def _deploy_target_pvc(
    *,
    vm_name: str,
    volume_spec: CbtVolumeRestoreSpec,
    namespace: str,
    client: DynamicClient,
) -> PersistentVolumeClaim:
    """Create an empty PVC large enough for the backup image."""
    pvc = PersistentVolumeClaim(
        name=f"cbt-rst-{vm_name}",
        namespace=namespace,
        client=client,
        accessmodes=volume_spec.access_mode,
        size=volume_spec.size,
        storage_class=volume_spec.storage_class,
        volume_mode=volume_spec.volume_mode,
    )
    LOGGER.info(f"Creating restore target PVC {pvc.name} for VM {vm_name}")
    pvc.deploy()
    return pvc


def _deploy_restored_vm(
    *,
    vm_name: str,
    target_pvc: PersistentVolumeClaim,
    namespace: str,
    client: DynamicClient,
) -> VirtualMachineForTests:
    """Create a halted VM that boots the restored disk under the backup's VM name.

    A VirtualMachineBackup does not store instancetype, preference, or OS.
    The VM uses the CBT VM profile, the same one the source VM fixture uses.
    """
    restored_vm = VirtualMachineForTests(
        name=vm_name,
        namespace=namespace,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=CBT_INSTANCE_TYPE_NAME),
        vm_preference=VirtualMachineClusterPreference(client=client, name=CBT_PREFERENCE_NAME),
        pvc=target_pvc,
        os_flavor=CBT_OS_FLAVOR,
        label=CBT_ENABLED_LABEL,
        generate_unique_name=False,
    )
    restored_vm.deploy()
    return restored_vm


def _read_linux_guest_file(vm: VirtualMachineForTests, filename: str) -> str:
    """Return the text of a regular file inside a Linux guest."""
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"cat {filename}"),
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )[0]
    return str(output)


def _files_for_backup(
    qcow2_files: list[str],
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
) -> list[str]:
    """Return qcow2 paths that identify one backup.

    The backup directory name contains the backup name or the checkpoint name.
    """
    matched = [path for path in qcow2_files if backup_name in path or checkpoint_name in path]
    vm_matched = [path for path in matched if vm_name in path]
    if vm_matched:
        return vm_matched
    return matched


def _select_volume_qcow2(
    *,
    qcow2_files: list[str],
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
    volume_name: str,
) -> str:
    """Return the qcow2 path for one volume in the full backup."""
    exact_candidates = [
        f"{CBT_BACKUP_DIR}/{vm_name}/{backup_name}/{volume_name}.qcow2",
        f"{CBT_BACKUP_DIR}/{vm_name}/{checkpoint_name}/{volume_name}.qcow2",
        f"{CBT_BACKUP_DIR}/{backup_name}/{volume_name}.qcow2",
        f"{CBT_BACKUP_DIR}/{checkpoint_name}/{volume_name}.qcow2",
    ]
    for candidate in exact_candidates:
        if candidate in qcow2_files:
            return candidate
    matched = _files_for_backup(
        qcow2_files=qcow2_files,
        vm_name=vm_name,
        backup_name=backup_name,
        checkpoint_name=checkpoint_name,
    )
    exact_names = [path for path in matched if Path(path).stem == volume_name]
    if len(exact_names) == 1:
        return exact_names[0]
    containing_names = [path for path in matched if volume_name in Path(path).name]
    if len(containing_names) == 1:
        return containing_names[0]
    listing = "\n".join(qcow2_files) if qcow2_files else "<none>"
    raise RuntimeError(
        f"Could not find one qcow2 for volume {volume_name} in backup {backup_name} "
        f"(checkpoint {checkpoint_name}). Files:\n{listing}"
    )


def _qcow2_virtual_size_bytes(*, pod: Pod, qcow2_file: str) -> int:
    """Return the guest-visible size of a qcow2 file."""
    output = pod.execute(
        command=["qemu-img", "info", "--output=json", "--force-share", qcow2_file],
        timeout=TIMEOUT_2MIN,
    )
    return int(json.loads(output)["virtual-size"])


def _target_pvc_size(*, virtual_size_bytes: int, volume_mode: str) -> str:
    """Return the target PVC capacity for the backup image.

    A Filesystem PVC needs extra capacity so the raw disk.img fits beside filesystem metadata.
    A block device is used as the disk itself, so it is only rounded up to the image size.
    """
    headroom_gib = CBT_FILESYSTEM_RESTORE_HEADROOM_GIB if volume_mode == PersistentVolumeClaim.VolumeMode.FILE else 0
    return cbt_pvc_size_with_headroom(source_disk_size=f"{virtual_size_bytes}", headroom_gib=headroom_gib)


def _list_qcow2_files(pod: Pod) -> list[str]:
    """Return every qcow2 file under the backup mount."""
    output = pod.execute(
        command=["find", CBT_BACKUP_DIR, "-name", "*.qcow2", "-type", "f"],
        timeout=TIMEOUT_2MIN,
    )
    qcow2_files = [line.strip() for line in output.splitlines() if line.strip()]
    if qcow2_files:
        return qcow2_files
    listing = pod.execute(
        command=["find", CBT_BACKUP_DIR, "-type", "f"],
        timeout=TIMEOUT_2MIN,
    )
    raise RuntimeError(f"No qcow2 files under {CBT_BACKUP_DIR}. Files:\n{listing}")


@contextmanager
def _push_restore_pod(
    *,
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    volume_devices: list[dict[str, Any]],
) -> Generator[Pod]:
    """Start a pod that mounts the backup PVC and, when given, the restore target."""
    container_spec: dict[str, Any] = {
        **POD_CONTAINER_SPEC,
        "name": "cbt-push-restore",
        "volumeMounts": volume_mounts,
    }
    if volume_devices:
        container_spec["volumeDevices"] = volume_devices
    with Pod(
        name=pod_name,
        namespace=namespace,
        client=client,
        containers=[container_spec],
        volumes=volumes,
        security_context=CBT_RUNNER_POD_SECURITY_CONTEXT,
    ) as restore_pod:
        LOGGER.info(f"Starting CBT push restore pod {pod_name} in {namespace}")
        try:
            restore_pod.wait_for_status(
                status=Pod.Status.RUNNING,
                timeout=TIMEOUT_5MIN,
                sleep=TIMEOUT_5SEC,
            )
        except TimeoutExpiredError as wait_error:
            restore_pod.get()
            status = restore_pod.instance.to_dict().get("status", {})
            raise RuntimeError(
                f"CBT push restore pod {restore_pod.name} did not start: {wait_error}. status={status}"
            ) from wait_error
        yield restore_pod
