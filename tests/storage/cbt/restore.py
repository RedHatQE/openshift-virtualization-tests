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
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from timeout_sampler import TimeoutExpiredError

from tests.storage.cbt.constants import (
    CBT_BACKUP_DIR,
    CBT_BACKUP_PVC_VOLUME_NAME,
    CBT_BACKUP_TYPE_FULL,
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_ENABLED_LABEL,
    CBT_FILESYSTEM_RESTORE_HEADROOM_PERCENT,
    CBT_FILESYSTEM_RESTORE_MIN_HEADROOM_GIB,
    CBT_TARGET_DEVICE_PATH,
    CBT_TARGET_MOUNT_PATH,
    CBT_TARGET_VOLUME_NAME,
    CBT_TEST_DATA,
)
from tests.storage.cbt.utils import BYTES_PER_GIB, cbt_pvc_size_with_headroom
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL
from utilities.constants.networking import POD_CONTAINER_SPEC
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_30MIN
from utilities.storage import run_command_on_vm_and_check_output
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from collections.abc import Generator

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine_backup import VirtualMachineBackup

LOGGER = logging.getLogger(__name__)


class CbtRestoreError(Exception):
    """A CBT push restore failed.

    Raised when a backup assumption is not met, a required backup resource is missing,
    the qcow2 cannot be selected or its virtual size cannot be read, or a restore PVC bind,
    restore pod start, or cleanup wait times out.
    """


# restricted-v2 assigns the namespace UID and fsGroup. Leave runAsUser, fsGroup,
# and hostUsers unset so admission succeeds and the container can call setgroups.
CBT_RUNNER_POD_SECURITY_CONTEXT: dict[str, Any] = {
    "seccompProfile": {"type": "RuntimeDefault"},
    "runAsNonRoot": True,
}


@dataclass(frozen=True)
class CbtVolumeRestoreSpec:
    """Volume from the backup and the PVC that will hold the restored raw disk.

    Attributes:
        volume_name: Name of the backed-up volume.
        size: Target PVC capacity as a Kubernetes quantity string, such as ``20Gi``.
        storage_class: Storage class of the restored disk.
        volume_mode: ``Filesystem`` or ``Block``.
        access_mode: Access mode from the storage class profile, such as ``ReadWriteOnce``.
    """

    volume_name: str
    size: str
    storage_class: str
    volume_mode: str
    access_mode: str


@dataclass(frozen=True)
class _RestoredDiskStorageClassProperties:
    """Storage class of the restored disk, and the volume mode and access mode of that class.

    The restored disk uses the source VM boot disk's storage class.
    """

    storage_class: str
    volume_mode: str
    access_mode: str


def assert_restored_rhel_vm_data(vm: VirtualMachineForTests) -> None:
    """Assert a restored RHEL VM still has the Linux boot-disk test file.

    The restored VM is always RHEL, so this helper reads the Linux guest path.
    It does not cover a Windows guest.

    Args:
        vm: Running restored RHEL VM.

    Raises:
        AssertionError: When the guest file is missing or has different content.
    """
    run_command_on_vm_and_check_output(
        vm=vm,
        command=f"cat {CBT_BOOT_DISK_TEST_DATA_FILE}",
        expected_result=CBT_TEST_DATA,
    )


@contextmanager
def restored_cbt_vm_from_push_backup(
    backups: list[VirtualMachineBackup],
    backup_pvc_name: str,
    storage_class: str,
    namespace: str,
    client: DynamicClient,
) -> Generator[VirtualMachineForTests]:
    """Rebuild the boot disk from the full push backup and start a VM with the backup's VM name.

    The caller deletes the source VM first. This function reads the backup and the source VM
    storage class's storage profile.

    Args:
        backups: Completed push backups. A full-backup restore contains exactly one backup.
        backup_pvc_name: PVC that holds the qcow2 backup.
        storage_class: Storage class of the source VM boot disk. The restored disk uses this class.
        namespace: Namespace for the restored VM and target PVC.
        client: Client used to create the restored VM, PVC, and restore pod.

    Yields:
        VirtualMachineForTests: Running restored VM.

    Side effects:
        Writes the restored boot disk, and deletes the restored VM and target PVC on exit.

    Raises:
        CbtRestoreError: When the backup count, type, or volume list is not one full volume; the backup
            or tracker is missing; the source disk storage class has no StorageProfile or claim property
            set; the backup does not contain one matching qcow2; qemu-img info does not return its virtual
            size; the restore PVC does not bind; the restore pod does not start; or the restored VM or
            target PVC is not deleted before the wait timeout. A cleanup failure is logged instead when
            another error is already propagating.
    """
    backup = _single_full_backup(backups=backups)
    vm_name = _backed_up_vm_name(backup=backup, namespace=namespace, client=client)
    volume_name = _full_backup_volume_name(backup=backup)
    disk_storage = _get_restored_disk_storage_class_properties(
        storage_class=storage_class,
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
        size=_target_pvc_size(virtual_size_bytes=virtual_size_bytes, volume_mode=disk_storage.volume_mode),
        storage_class=disk_storage.storage_class,
        volume_mode=disk_storage.volume_mode,
        access_mode=disk_storage.access_mode,
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
        earlier_failure = sys.exc_info()[0] is not None
        cleanup_errors: list[Exception] = []
        if restored_vm is not None:
            try:
                restored_vm.clean_up(wait=True)
                require_vm_deleted(vm=restored_vm)
            except Exception as cleanup_error:
                # Aggregate cleanup failures so one does not hide another or an earlier test error.
                cleanup_errors.append(cleanup_error)
        if target_pvc is not None:
            try:
                if not target_pvc.clean_up(wait=True):
                    raise CbtRestoreError(f"Timed out deleting restore PVC {namespace}/{target_pvc.name}")
            except Exception as cleanup_error:
                # Aggregate cleanup failures so one does not hide another or an earlier test error.
                cleanup_errors.append(cleanup_error)
        if earlier_failure:
            for reported_error in cleanup_errors:
                LOGGER.error(f"Restore cleanup failed: {reported_error}")
        else:
            for reported_error in cleanup_errors[1:]:
                LOGGER.error(f"Restore cleanup failed: {reported_error}")
            if cleanup_errors:
                raise cleanup_errors[0]


def require_vm_deleted(vm: VirtualMachineForTests) -> None:
    """Raise when a VM is still present after cleanup.

    VirtualMachineForTests.clean_up unconditionally returns True and does not
    report a deletion timeout, so VM existence must be checked separately.

    Args:
        vm: VM whose deletion was just attempted.

    Raises:
        CbtRestoreError: When the VM still exists.
    """
    if vm.exists:
        raise CbtRestoreError(f"Timed out deleting VM {vm.namespace}/{vm.name}")


def _single_full_backup(backups: list[VirtualMachineBackup]) -> VirtualMachineBackup:
    """Return the one backup a full restore can apply."""
    if len(backups) != 1:
        backup_names = [backup.name for backup in backups]
        raise CbtRestoreError(f"Push full restore expects one backup, got {len(backups)}: {backup_names}")
    return backups[0]


def _backed_up_vm_name(backup: VirtualMachineBackup, namespace: str, client: DynamicClient) -> str:
    """Return the VM name recorded on the backup or its tracker.

    Raises:
        CbtRestoreError: When the backup or its tracker has no source VM. The original lookup error is chained.
    """
    try:
        source = backup.instance.to_dict()["spec"]["source"]
        source_name = str(source["name"])
        source_kind = source["kind"]
    except NotFoundError as missing_backup:
        raise CbtRestoreError(f"Backup {backup.name} not found") from missing_backup
    except KeyError as missing_field:
        raise CbtRestoreError(f"Backup {backup.name} has no source VM ({missing_field})") from missing_field
    if source_kind != VirtualMachineBackupTracker.kind:
        return source_name
    tracker = VirtualMachineBackupTracker(name=source_name, namespace=namespace, client=client)
    try:
        return str(tracker.instance.to_dict()["spec"]["source"]["name"])
    except NotFoundError as missing_tracker:
        raise CbtRestoreError(f"Backup tracker {source_name} not found in namespace {namespace}") from missing_tracker
    except KeyError as missing_field:
        raise CbtRestoreError(f"Backup tracker {source_name} has no source VM ({missing_field})") from missing_field


def _full_backup_volume_name(backup: VirtualMachineBackup) -> str:
    """Return the single volume recorded on a full backup.

    Backup type is ``status.type``. ``includedVolumes`` entries carry only ``volumeName``.

    Raises:
        CbtRestoreError: When the backup is missing, is not full, or does not record exactly one volume.
            The original lookup error is chained.
    """
    try:
        status = backup.instance.to_dict()["status"]
        backup_type = status["type"]
        included_volumes = status["includedVolumes"]
    except NotFoundError as missing_backup:
        raise CbtRestoreError(f"Backup {backup.name} not found") from missing_backup
    except KeyError as missing_field:
        raise CbtRestoreError(f"Backup {backup.name} is missing {missing_field}") from missing_field
    if backup_type != CBT_BACKUP_TYPE_FULL:
        raise CbtRestoreError(f"Backup {backup.name} type is {backup_type!r}, expected {CBT_BACKUP_TYPE_FULL!r}")
    try:
        volume_names = [str(volume["volumeName"]) for volume in included_volumes]
    except KeyError as missing_field:
        raise CbtRestoreError(f"Backup {backup.name} volume is missing {missing_field}") from missing_field
    if len(volume_names) != 1:
        raise CbtRestoreError(f"Backup {backup.name} full restore expects one volume, got {volume_names}")
    return volume_names[0]


def _get_restored_disk_storage_class_properties(
    storage_class: str, client: DynamicClient
) -> _RestoredDiskStorageClassProperties:
    """Return the restored disk's storage class and that class's disk claim shape.

    Raises:
        CbtRestoreError: When the StorageProfile does not exist or has no claim property set.
            A lookup error is chained when one was raised.
    """
    profile = StorageProfile(name=storage_class, client=client)
    try:
        volume_mode = profile.first_claim_property_set_volume_mode()
        access_modes = profile.first_claim_property_set_access_modes()
    except NotFoundError as missing_profile:
        raise CbtRestoreError(f"StorageProfile {storage_class} not found") from missing_profile
    if not volume_mode or not access_modes:
        raise CbtRestoreError(f"StorageProfile {storage_class} has no claim property set")
    return _RestoredDiskStorageClassProperties(
        storage_class=storage_class,
        volume_mode=volume_mode,
        access_mode=access_modes[0],
    )


def _target_file(volume_mode: str) -> str:
    """Return the in-pod path of the disk being restored."""
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return CBT_TARGET_DEVICE_PATH
    return f"{CBT_TARGET_MOUNT_PATH}/disk.img"


def _target_pod_volumes(
    pvc_name: str,
    volume_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return volume mounts, devices, and volumes for the restore target PVC."""
    volumes = [{"name": CBT_TARGET_VOLUME_NAME, "persistentVolumeClaim": {"claimName": pvc_name}}]
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return [], [{"name": CBT_TARGET_VOLUME_NAME, "devicePath": CBT_TARGET_DEVICE_PATH}], volumes
    return [{"name": CBT_TARGET_VOLUME_NAME, "mountPath": CBT_TARGET_MOUNT_PATH}], [], volumes


def _inspect_backup_qcow2(
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
    vm_name: str,
    volume_spec: CbtVolumeRestoreSpec,
    target_pvc: PersistentVolumeClaim,
    backup_pvc_name: str,
    qcow2_file: str,
    namespace: str,
    client: DynamicClient,
) -> None:
    """Write the full push-mode qcow2 onto the target PVC.

    The restore pod consumes the target PVC, so the Bound wait runs after that pod exists.
    A WaitForFirstConsumer storage class does not bind until then.

    Raises:
        CbtRestoreError: When the target PVC is not Bound before the wait timeout.
            The original timeout is chained.
    """
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
        try:
            target_pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_5MIN)
        except TimeoutExpiredError as wait_error:
            raise CbtRestoreError(f"Restore PVC {target_pvc.namespace}/{target_pvc.name} is not Bound") from wait_error
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


def _backup_pod_volumes(backup_pvc_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the mount and volume for the backup PVC."""
    return (
        [{"name": CBT_BACKUP_PVC_VOLUME_NAME, "mountPath": CBT_BACKUP_DIR, "readOnly": True}],
        [{"name": CBT_BACKUP_PVC_VOLUME_NAME, "persistentVolumeClaim": {"claimName": backup_pvc_name}}],
    )


def _deploy_target_pvc(
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
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=client, name=RHEL9_PREFERENCE),
        pvc=target_pvc,
        os_flavor=OS_FLAVOR_RHEL,
        label=CBT_ENABLED_LABEL,
        generate_unique_name=False,
    )
    restored_vm.deploy()
    return restored_vm


def _files_for_backup(
    qcow2_files: list[str],
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
) -> list[str]:
    """Return qcow2 paths whose directory components identify one backup.

    A directory component must equal the backup name or the checkpoint name.
    Paths that also have the VM name as a directory component are preferred.
    """
    matched = [
        path for path in qcow2_files if backup_name in Path(path).parts[:-1] or checkpoint_name in Path(path).parts[:-1]
    ]
    vm_matched = [path for path in matched if vm_name in Path(path).parts[:-1]]
    if vm_matched:
        return vm_matched
    return matched


def _select_volume_qcow2(
    qcow2_files: list[str],
    vm_name: str,
    backup_name: str,
    checkpoint_name: str,
    volume_name: str,
) -> str:
    """Return the one qcow2 for this volume in the full backup.

    KubeVirt writes ``<vm>/<checkpoint>/<backup>-<volume>.qcow2``. A file whose
    stem is exactly ``<backup>-<volume>`` or the volume name is accepted when it
    is the only match for that backup.

    Raises:
        CbtRestoreError: When the backup does not contain exactly one matching qcow2.
    """
    matched = _files_for_backup(
        qcow2_files=qcow2_files,
        vm_name=vm_name,
        backup_name=backup_name,
        checkpoint_name=checkpoint_name,
    )
    exact_stems = {volume_name, f"{backup_name}-{volume_name}"}
    exact_names = [path for path in matched if Path(path).stem in exact_stems]
    if len(exact_names) == 1:
        return exact_names[0]
    listing = "\n".join(qcow2_files) if qcow2_files else "<none>"
    raise CbtRestoreError(
        f"Could not find one qcow2 for volume {volume_name} in backup {backup_name} "
        f"(checkpoint {checkpoint_name}). Files:\n{listing}"
    )


def _qcow2_virtual_size_bytes(pod: Pod, qcow2_file: str) -> int:
    """Return the guest-visible size of a qcow2 file.

    Raises:
        CbtRestoreError: When qemu-img info does not return a virtual-size. The original parse error is chained.
    """
    output = pod.execute(
        command=["qemu-img", "info", "--output=json", "--force-share", qcow2_file],
        timeout=TIMEOUT_2MIN,
    )
    try:
        return int(json.loads(output)["virtual-size"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as parse_error:
        raise CbtRestoreError(
            f"Could not read virtual-size from qemu-img info for {qcow2_file}: {output}"
        ) from parse_error


def _target_pvc_size(virtual_size_bytes: int, volume_mode: str) -> str:
    """Return the target PVC capacity for the backup image.

    A Filesystem PVC is 6% larger than the disk, rounded up to at least 1 Gi, so the raw
    disk.img fits for a non-root writer. ext4 reserves 5% for root.
    A block device is used as the disk itself, so it is only rounded up to the image size.
    """
    headroom_gib = 0
    if volume_mode == PersistentVolumeClaim.VolumeMode.FILE:
        source_gib = (virtual_size_bytes + BYTES_PER_GIB - 1) // BYTES_PER_GIB
        proportional_headroom_gib = (source_gib * CBT_FILESYSTEM_RESTORE_HEADROOM_PERCENT + 99) // 100
        headroom_gib = max(CBT_FILESYSTEM_RESTORE_MIN_HEADROOM_GIB, proportional_headroom_gib)
    return cbt_pvc_size_with_headroom(source_disk_size=f"{virtual_size_bytes}", headroom_gib=headroom_gib)


def _list_qcow2_files(pod: Pod) -> list[str]:
    """Return every qcow2 file under the backup mount.

    Raises:
        CbtRestoreError: When the backup mount contains no qcow2 files.
    """
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
    raise CbtRestoreError(f"No qcow2 files under {CBT_BACKUP_DIR}. Files:\n{listing}")


@contextmanager
def _push_restore_pod(
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    volume_devices: list[dict[str, Any]],
) -> Generator[Pod]:
    """Start a pod that mounts the backup PVC and, when given, the restore target.

    Yields:
        Pod: Running restore pod.

    Raises:
        CbtRestoreError: When the pod is not Running before the wait timeout. The original timeout is chained.
            A pod that is gone before its status can be read is reported in that error.
    """
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
            try:
                status = restore_pod.instance.to_dict().get("status", {})
            except NotFoundError:
                status = "<pod not found>"
            raise CbtRestoreError(
                f"CBT push restore pod {restore_pod.name} did not start: {wait_error}. status={status}"
            ) from wait_error
        yield restore_pod
