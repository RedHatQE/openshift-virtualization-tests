"""CBT backup integrity restore.

OpenShift Virtualization has no restore API for changed-block-tracking backups.
These helpers rebuild VM disks from a push-mode qcow2 chain or from pull-mode
client storage, start the VM, and let tests confirm the guest data survived.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import shlex
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.utils.quantity import parse_quantity
from ocp_resources.config_map import ConfigMap
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError

from tests.storage.cbt.constants import (
    CBT_DATA_DISK_TEST_DATA,
    CBT_ENABLED_LABEL,
    CBT_TEST_DATA,
    CBT_WINDOWS_PERSISTENT_DEVICE_PARAMS,
    CBT_WINDOWS_VERSION,
)
from tests.storage.cbt.pull_collect_runner import PULL_COLLECT_PARAMS_ENV
from tests.storage.cbt.pull_restore_runner import PULL_RESTORE_PARAMS_ENV
from tests.storage.cbt.push_restore_runner import PUSH_RESTORE_PARAMS_ENV
from tests.storage.cbt.utils import (
    cbt_boot_disk_test_data_file,
    cbt_data_disk_volume_names,
    guest_device_path_for_volume,
    incremental_test_data,
    incremental_test_data_file,
    is_windows_cbt_vm,
)
from utilities.constants.networking import NET_UTIL_CONTAINER_IMAGE, POD_CONTAINER_SPEC
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_10MIN, TIMEOUT_30MIN
from utilities.constants.virt import DV_DISK
from utilities.storage import verify_file_in_windows_vm
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_windows_vm

LOGGER = logging.getLogger(__name__)

# The unprivileged test user can only admit restricted-v2/v3 pods. Those SCCs
# assign the namespace UID and fsGroup, and restricted-v3 requires hostUsers=false.
# Pinning qemu uid 1000 and gid 107 is rejected.
CBT_RUNNER_POD_SECURITY_CONTEXT: dict[str, Any] = {
    "seccompProfile": {"type": "RuntimeDefault"},
    "runAsNonRoot": True,
    "hostUsers": False,
}

BACKUP_DIR = "/backup"
TARGET_VOLUME_NAME = "target-disk"
TARGET_MOUNT_PATH = "/target"
TARGET_DEVICE_PATH = "/dev/target-disk"
BACKUP_PVC_VOLUME_NAME = "backup-src"
RESTORE_WORK_VOLUME_NAME = "restore-work"
RESTORE_WORK_MOUNT_PATH = "/work"
PULL_CA_CERT_PATH = "/tmp/backup-ca.crt"
PULL_MAP_SCAN_LIMIT_BYTES = 1 << 30
PULL_COLLECT_CHUNK_SIZE_BYTES = 256 * 1024 * 1024
PULL_MAP_HOLE_DESCRIPTIONS = ["hole", "zero"]
PULL_FULL_BACKUP_MIN_COLLECTED_BYTES = 100 * 1024 * 1024
BLOCK_DEVICE_READ_BYTES = 256


@dataclass(frozen=True)
class CbtVolumeRestoreSpec:
    """Disk identity and PVC shape copied from a source volume before the VM is deleted."""

    volume_name: str
    claim_name: str
    size: str
    storage_class: str
    volume_mode: str
    access_mode: str


class CollectedPullBackups:
    """Pull backups captured for status checks, plus the PVC that holds their raw data."""

    def __init__(self, backups: list[tuple[str, dict[str, Any]]], client_pvc_name: str) -> None:
        self.backups = backups
        self.client_pvc_name = client_pvc_name


class ConcurrentCollectedPullBackups:
    """Concurrent pull backup status captured before the exports were deleted, plus one client PVC per VM."""

    def __init__(self, backups: list[tuple[str, dict[str, Any]]], client_pvc_names: list[str]) -> None:
        self.backups = backups
        self.client_pvc_names = client_pvc_names


class RestoredCbtVm(VirtualMachineForTests):
    """Restored CBT VM whose boot PVC is ``pvc`` and whose extra disks keep their original names."""

    def __init__(self, restored_data_disks: list[tuple[str, PersistentVolumeClaim]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.restored_data_disks = restored_data_disks

    def to_dict(self) -> None:
        """Add restored data-disk PVCs after the boot disk.

        Note:
            Do not call more than once. Each call appends the data disks again.
        """
        super().to_dict()
        template_spec = self.res["spec"]["template"]["spec"]
        disks = template_spec["domain"]["devices"]["disks"]
        volumes = template_spec["volumes"]
        for volume_name, pvc in self.restored_data_disks:
            disks.append({"disk": {"bus": self.disk_type}, "name": volume_name})
            volumes.append({"name": volume_name, "persistentVolumeClaim": {"claimName": pvc.name}})


def pull_export_token(secret: Secret) -> str:
    """Return the raw pull-mode export token stored in a Secret.

    Args:
        secret: Secret whose ``token`` data is the export credential.

    Returns:
        str: Decoded token value.
    """
    return base64.b64decode(secret.instance.data["token"]).decode("utf-8")


def cbt_volumes_to_restore(vm: VirtualMachineForTests) -> list[str]:
    """Boot disk, then every CBT data disk. Persistent vTPM and EFI volumes are left out.

    Args:
        vm: Source VM whose disks were backed up.

    Returns:
        list[str]: Volume names to collect and restore, boot disk first.
    """
    return [DV_DISK, *cbt_data_disk_volume_names(vm=vm)]


def cbt_volume_restore_spec(vm: VirtualMachineForTests, volume_name: str) -> CbtVolumeRestoreSpec:
    """Read the live PVC shape for one VM volume.

    Args:
        vm: Running VM that still owns the source PVC.
        volume_name: VM volume to inspect.

    Returns:
        CbtVolumeRestoreSpec: Size, storage class, volume mode, and access mode of that PVC.
    """
    claim_name = _claim_name_for_volume(vm=vm, volume_name=volume_name)
    pvc = PersistentVolumeClaim(name=claim_name, namespace=vm.namespace, client=vm.client)
    spec = pvc.instance.to_dict()["spec"]
    return CbtVolumeRestoreSpec(
        volume_name=volume_name,
        claim_name=claim_name,
        size=spec["resources"]["requests"]["storage"],
        storage_class=spec["storageClassName"],
        volume_mode=spec.get("volumeMode", PersistentVolumeClaim.VolumeMode.FILE),
        access_mode=spec["accessModes"][0],
    )


def collect_cbt_pull_backup(
    *,
    backup: VirtualMachineBackup,
    vm: VirtualMachineForTests,
    export_token: str,
    client_backup_pvc_name: str,
    volume_names: list[str],
    checkpoint_index: int,
) -> None:
    """Download one ready pull-mode backup onto the client PVC.

    The source VM must still exist so each volume's PVC size can be read.
    Incremental checkpoints are seeded from the previous raw file for that volume.

    Args:
        backup: Pull-mode backup whose export is ready.
        vm: VM that owns the backed-up volumes.
        export_token: Raw token from the pull-mode Secret.
        client_backup_pvc_name: Filesystem PVC that stores raw snapshots.
        volume_names: Volumes to download, in restore order.
        checkpoint_index: Zero-based position of this backup in the chain.

    Side effects:
        Runs one collect pod per volume. Each pod writes a raw file on the client PVC.
    """
    status = backup.instance.to_dict()["status"]
    force_full_backup = bool(backup.instance.to_dict()["spec"].get("forceFullBackup", False))
    checkpoint_name = status.get("checkpointName")
    endpoint_cert = status.get("endpointCert")
    if not checkpoint_name:
        raise RuntimeError(f"Backup {backup.name} status has no checkpointName")
    if not endpoint_cert:
        raise RuntimeError(f"Backup {backup.name} status has no endpointCert")
    LOGGER.info(f"Collecting pull backup {backup.name} checkpoint {checkpoint_index} ({checkpoint_name})")
    for volume_name in volume_names:
        included_volume = _included_volume(backup_name=backup.name, status=status, volume_name=volume_name)
        volume_spec = cbt_volume_restore_spec(vm=vm, volume_name=volume_name)
        raw_file = _pull_raw_file_path(
            volume_name=volume_name,
            checkpoint_index=checkpoint_index,
            checkpoint_name=str(checkpoint_name),
        )
        _run_python_runner_pod(
            pod_name=_short_pod_name(prefix="cbt-col", identity=f"{backup.name}-{volume_name}"),
            namespace=backup.namespace,
            client=backup.client,
            runner_script_filename="pull_collect_runner.py",
            container_name="cbt-pull-collect",
            params_env_name=PULL_COLLECT_PARAMS_ENV,
            runner_params={
                "endpoint_cert": endpoint_cert,
                "export_token": export_token,
                "map_endpoint": included_volume["mapEndpoint"],
                "data_endpoint": included_volume["dataEndpoint"],
                "disk_size_bytes": int(parse_quantity(quantity=volume_spec.size)),
                "raw_file": raw_file,
                "volume_backup_dir": f"{BACKUP_DIR}/{volume_name}",
                "force_full_backup": force_full_backup,
                "enforce_min_collected_bytes": volume_name == DV_DISK and force_full_backup,
                "pull_ca_cert_path": PULL_CA_CERT_PATH,
                "pull_map_scan_limit_bytes": PULL_MAP_SCAN_LIMIT_BYTES,
                "pull_collect_chunk_size_bytes": PULL_COLLECT_CHUNK_SIZE_BYTES,
                "pull_map_hole_descriptions": PULL_MAP_HOLE_DESCRIPTIONS,
                "pull_full_backup_min_collected_bytes": PULL_FULL_BACKUP_MIN_COLLECTED_BYTES,
            },
            volume_mounts=[{"name": BACKUP_PVC_VOLUME_NAME, "mountPath": BACKUP_DIR}],
            volumes=[{"name": BACKUP_PVC_VOLUME_NAME, "persistentVolumeClaim": {"claimName": client_backup_pvc_name}}],
            wait_timeout=TIMEOUT_30MIN,
            pod_role="pull collect",
        )


def assert_restored_cbt_vm_data(
    vm: VirtualMachineForTests,
    incremental_indexes: list[int] | None = None,
    data_disk_names: list[str] | None = None,
) -> None:
    """Assert a restored VM still has the guest data written before its backups.

    Args:
        vm: Running restored VM.
        incremental_indexes: 1-based incremental files that must be present. Omit when the
            restored backup chain has no incremental guest data.
        data_disk_names: Data-disk volume names whose block contents must match the
            original data-disk payload.
    """
    _assert_guest_file(vm=vm, filename=cbt_boot_disk_test_data_file(vm=vm), content=CBT_TEST_DATA)
    for incremental_index in incremental_indexes or []:
        _assert_guest_file(
            vm=vm,
            filename=incremental_test_data_file(index=incremental_index, vm=vm),
            content=incremental_test_data(index=incremental_index),
        )
    for disk_name in data_disk_names or []:
        _assert_guest_file(
            vm=vm,
            filename=guest_device_path_for_volume(vm=vm, volume_name=disk_name),
            content=CBT_DATA_DISK_TEST_DATA,
        )


@contextmanager
def restored_cbt_vm_from_push_backup(
    *,
    vm: VirtualMachineForTests,
    backups: list[VirtualMachineBackup],
    backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
) -> Generator[VirtualMachineForTests]:
    """Delete the source VM, rebuild its disks from the push chain, and start it.

    Args:
        vm: Source VM. Deleted before the restored VM reuses its name.
        backups: Completed push backups in chain order, full backup first.
        backup_pvc_name: PVC that holds the qcow2 chain.
        namespace: Namespace for the restored VM and target PVCs.
        client: Client used to create the restored VM, PVCs, and restore pods.

    Yields:
        VirtualMachineForTests: Running restored VM.

    Side effects:
        Deletes the source VM, writes restored disks, and deletes the restored VM and
        target PVCs on exit.
    """
    volume_specs = [cbt_volume_restore_spec(vm=vm, volume_name=name) for name in cbt_volumes_to_restore(vm=vm)]
    chain = [_push_chain_entry(backup=backup) for backup in backups]
    identity = _vm_restore_identity(vm=vm)
    LOGGER.info(f"Deleting VM {vm.name} before push restore")
    vm.clean_up(wait=True)
    vm.teardown = False
    yield from _start_restored_vm(
        identity=identity,
        volume_specs=volume_specs,
        namespace=namespace,
        client=client,
        restore_one_volume=lambda volume_spec, target_pvc: _restore_push_volume(
            identity=identity,
            volume_spec=volume_spec,
            target_pvc=target_pvc,
            backup_pvc_name=backup_pvc_name,
            chain=chain,
            namespace=namespace,
            client=client,
        ),
    )


@contextmanager
def restored_cbt_vm_from_pull_backup(
    *,
    vm: VirtualMachineForTests,
    client_backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
) -> Generator[VirtualMachineForTests]:
    """Delete the source VM, rebuild its disks from pull client storage, and start it.

    Args:
        vm: Source VM. Deleted before the restored VM reuses its name.
        client_backup_pvc_name: PVC that holds collected raw snapshots.
        namespace: Namespace for the restored VM and target PVCs.
        client: Client used to create the restored VM, PVCs, and restore pods.

    Yields:
        VirtualMachineForTests: Running restored VM.

    Side effects:
        Deletes the source VM, writes restored disks, and deletes the restored VM and
        target PVCs on exit.
    """
    volume_specs = [cbt_volume_restore_spec(vm=vm, volume_name=name) for name in cbt_volumes_to_restore(vm=vm)]
    identity = _vm_restore_identity(vm=vm)
    LOGGER.info(f"Deleting VM {vm.name} before pull restore")
    vm.clean_up(wait=True)
    vm.teardown = False
    yield from _start_restored_vm(
        identity=identity,
        volume_specs=volume_specs,
        namespace=namespace,
        client=client,
        restore_one_volume=lambda volume_spec, target_pvc: _restore_pull_volume(
            identity=identity,
            volume_spec=volume_spec,
            target_pvc=target_pvc,
            client_backup_pvc_name=client_backup_pvc_name,
            namespace=namespace,
            client=client,
        ),
    )


def _claim_name_for_volume(vm: VirtualMachineForTests, volume_name: str) -> str:
    """Return the PVC or DataVolume name backing one VM volume."""
    for volume in vm.instance.to_dict()["spec"]["template"]["spec"]["volumes"]:
        if volume["name"] != volume_name:
            continue
        if "dataVolume" in volume:
            return str(volume["dataVolume"]["name"])
        if "persistentVolumeClaim" in volume:
            return str(volume["persistentVolumeClaim"]["claimName"])
        raise RuntimeError(f"Volume {volume_name} on VM {vm.name} is not a DataVolume or PVC")
    raise RuntimeError(f"VM {vm.name} has no volume {volume_name}")


def _included_volume(backup_name: str, status: dict[str, Any], volume_name: str) -> dict[str, Any]:
    """Return one includedVolumes entry, including its export endpoints."""
    for included_volume in status["includedVolumes"]:
        if included_volume["volumeName"] == volume_name:
            if not included_volume.get("mapEndpoint") or not included_volume.get("dataEndpoint"):
                raise RuntimeError(f"Backup {backup_name} volume {volume_name} is missing export endpoints")
            return included_volume
    raise RuntimeError(f"Backup {backup_name} does not include volume {volume_name}")


def _pull_checkpoint_dir_name(checkpoint_name: str) -> str:
    """Return a checkpoint directory name that stays stable in object paths."""
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", checkpoint_name)
    if iso_match:
        date_part, hour, minute, second = iso_match.groups()
        return f"{date_part}_{hour}-{minute}-{second}"
    return re.sub(r"[^\w.\-]", "_", checkpoint_name)


def _pull_raw_file_path(*, volume_name: str, checkpoint_index: int, checkpoint_name: str) -> str:
    """Return the client-storage path for one volume checkpoint."""
    directory = f"{checkpoint_index:02d}-{_pull_checkpoint_dir_name(checkpoint_name=checkpoint_name)}"
    return f"{BACKUP_DIR}/{volume_name}/{directory}/{volume_name}.raw"


def _push_chain_entry(backup: VirtualMachineBackup) -> dict[str, str]:
    """Return the backup and checkpoint names the push runner uses to find qcow2 files."""
    checkpoint_name = backup.instance.to_dict()["status"].get("checkpointName")
    if not checkpoint_name:
        raise RuntimeError(f"Backup {backup.name} status has no checkpointName")
    return {"backup_name": backup.name, "checkpoint_name": str(checkpoint_name)}


@dataclass(frozen=True)
class _VmRestoreIdentity:
    """Guest and scheduling fields copied off the source VM before it is deleted."""

    name: str
    instance_type_name: str
    preference_name: str
    os_flavor: str
    windows: bool


def _vm_restore_identity(vm: VirtualMachineForTests) -> _VmRestoreIdentity:
    """Capture the fields needed to recreate a VM after the source object is gone."""
    spec = vm.instance.to_dict()["spec"]
    return _VmRestoreIdentity(
        name=vm.name,
        instance_type_name=spec["instancetype"]["name"],
        preference_name=spec["preference"]["name"],
        os_flavor=vm.os_flavor,
        windows=is_windows_cbt_vm(vm=vm),
    )


def _short_pod_name(*, prefix: str, identity: str) -> str:
    """Return a DNS-safe pod name shorter than the 63-character limit."""
    digest = hashlib.sha256(identity.encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _target_file(volume_mode: str) -> str:
    """Return the in-pod path of the disk being restored."""
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return TARGET_DEVICE_PATH
    return f"{TARGET_MOUNT_PATH}/disk.img"


def _target_pod_volumes(
    *,
    pvc_name: str,
    volume_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return volume mounts, devices, and volumes for one restore target PVC."""
    volumes = [{"name": TARGET_VOLUME_NAME, "persistentVolumeClaim": {"claimName": pvc_name}}]
    if volume_mode == PersistentVolumeClaim.VolumeMode.BLOCK:
        return [], [{"name": TARGET_VOLUME_NAME, "devicePath": TARGET_DEVICE_PATH}], volumes
    return [{"name": TARGET_VOLUME_NAME, "mountPath": TARGET_MOUNT_PATH}], [], volumes


def _restore_push_volume(
    *,
    identity: _VmRestoreIdentity,
    volume_spec: CbtVolumeRestoreSpec,
    target_pvc: PersistentVolumeClaim,
    backup_pvc_name: str,
    chain: list[dict[str, str]],
    namespace: str,
    client: DynamicClient,
) -> None:
    """Write one volume's push-mode qcow2 chain onto its target PVC."""
    target_mounts, target_devices, target_volumes = _target_pod_volumes(
        pvc_name=target_pvc.name,
        volume_mode=volume_spec.volume_mode,
    )
    LOGGER.info(f"Restoring push volume {volume_spec.volume_name} for VM {identity.name}")
    _run_python_runner_pod(
        pod_name=_short_pod_name(prefix="cbt-rstr", identity=f"{identity.name}-{volume_spec.volume_name}-push"),
        namespace=namespace,
        client=client,
        runner_script_filename="push_restore_runner.py",
        container_name="cbt-push-restore",
        params_env_name=PUSH_RESTORE_PARAMS_ENV,
        runner_params={
            "backup_dir": BACKUP_DIR,
            "vm_name": identity.name,
            "volume_name": volume_spec.volume_name,
            "chain": chain,
            "volume_work_dir": f"{RESTORE_WORK_MOUNT_PATH}/{volume_spec.volume_name}",
            "target_file": _target_file(volume_mode=volume_spec.volume_mode),
        },
        volume_mounts=[
            *target_mounts,
            {"name": BACKUP_PVC_VOLUME_NAME, "mountPath": BACKUP_DIR, "readOnly": True},
            {"name": RESTORE_WORK_VOLUME_NAME, "mountPath": RESTORE_WORK_MOUNT_PATH},
        ],
        volume_devices=target_devices,
        volumes=[
            *target_volumes,
            {"name": BACKUP_PVC_VOLUME_NAME, "persistentVolumeClaim": {"claimName": backup_pvc_name}},
            {"name": RESTORE_WORK_VOLUME_NAME, "emptyDir": {}},
        ],
        wait_timeout=TIMEOUT_30MIN,
        pod_role="push restore",
    )


def _restore_pull_volume(
    *,
    identity: _VmRestoreIdentity,
    volume_spec: CbtVolumeRestoreSpec,
    target_pvc: PersistentVolumeClaim,
    client_backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
) -> None:
    """Write one volume's newest pull-mode raw snapshot onto its target PVC."""
    target_mounts, target_devices, target_volumes = _target_pod_volumes(
        pvc_name=target_pvc.name,
        volume_mode=volume_spec.volume_mode,
    )
    LOGGER.info(f"Restoring pull volume {volume_spec.volume_name} for VM {identity.name}")
    _run_python_runner_pod(
        pod_name=_short_pod_name(prefix="cbt-rstr", identity=f"{identity.name}-{volume_spec.volume_name}-pull"),
        namespace=namespace,
        client=client,
        runner_script_filename="pull_restore_runner.py",
        container_name="cbt-pull-restore",
        params_env_name=PULL_RESTORE_PARAMS_ENV,
        runner_params={
            "backup_dir": BACKUP_DIR,
            "volume_name": volume_spec.volume_name,
            "target_file": _target_file(volume_mode=volume_spec.volume_mode),
            "volume_mode": volume_spec.volume_mode,
        },
        volume_mounts=[
            *target_mounts,
            {"name": BACKUP_PVC_VOLUME_NAME, "mountPath": BACKUP_DIR, "readOnly": True},
        ],
        volume_devices=target_devices,
        volumes=[
            *target_volumes,
            {"name": BACKUP_PVC_VOLUME_NAME, "persistentVolumeClaim": {"claimName": client_backup_pvc_name}},
        ],
        wait_timeout=TIMEOUT_30MIN,
        pod_role="pull restore",
    )


def _deploy_target_pvc(
    *,
    identity: _VmRestoreIdentity,
    volume_spec: CbtVolumeRestoreSpec,
    namespace: str,
    client: DynamicClient,
) -> PersistentVolumeClaim:
    """Create an empty PVC shaped like one source volume."""
    pvc = PersistentVolumeClaim(
        name=_short_pod_name(prefix="cbt-rst", identity=f"{identity.name}-{volume_spec.volume_name}"),
        namespace=namespace,
        client=client,
        accessmodes=volume_spec.access_mode,
        size=volume_spec.size,
        storage_class=volume_spec.storage_class,
        volume_mode=volume_spec.volume_mode,
    )
    pvc.deploy()
    return pvc


def _start_restored_vm(
    *,
    identity: _VmRestoreIdentity,
    volume_specs: list[CbtVolumeRestoreSpec],
    namespace: str,
    client: DynamicClient,
    restore_one_volume: Callable[[CbtVolumeRestoreSpec, PersistentVolumeClaim], None],
) -> Generator[VirtualMachineForTests]:
    """Create target PVCs, restore each volume, start the VM, then delete it and the PVCs."""
    target_pvcs: list[PersistentVolumeClaim] = []
    restored_vm: VirtualMachineForTests | None = None
    try:
        for volume_spec in volume_specs:
            target_pvc = _deploy_target_pvc(
                identity=identity,
                volume_spec=volume_spec,
                namespace=namespace,
                client=client,
            )
            target_pvcs.append(target_pvc)
            restore_one_volume(volume_spec=volume_spec, target_pvc=target_pvc)
        restored_vm = _deploy_restored_vm(identity=identity, target_pvcs=target_pvcs, volume_specs=volume_specs)
        running_vm(
            vm=restored_vm,
            ssh_timeout=TIMEOUT_10MIN if identity.windows else TIMEOUT_5MIN,
        )
        if identity.windows:
            wait_for_windows_vm(vm=restored_vm, version=CBT_WINDOWS_VERSION)
        yield restored_vm
    finally:
        if restored_vm is not None and restored_vm.exists:
            restored_vm.clean_up(wait=True)
        for target_pvc in reversed(target_pvcs):
            if target_pvc.exists:
                target_pvc.clean_up(wait=True)


def _deploy_restored_vm(
    *,
    identity: _VmRestoreIdentity,
    target_pvcs: list[PersistentVolumeClaim],
    volume_specs: list[CbtVolumeRestoreSpec],
) -> VirtualMachineForTests:
    """Create a halted VM from the restored boot PVC and any restored data disks."""
    data_disks = list(zip(volume_specs[1:], target_pvcs[1:], strict=True))
    restored_vm = RestoredCbtVm(
        name=identity.name,
        namespace=target_pvcs[0].namespace,
        client=target_pvcs[0].client,
        vm_instance_type=VirtualMachineClusterInstancetype(
            client=target_pvcs[0].client,
            name=identity.instance_type_name,
        ),
        vm_preference=VirtualMachineClusterPreference(
            client=target_pvcs[0].client,
            name=identity.preference_name,
        ),
        pvc=target_pvcs[0],
        os_flavor=identity.os_flavor,
        label=CBT_ENABLED_LABEL,
        tpm_params=CBT_WINDOWS_PERSISTENT_DEVICE_PARAMS if identity.windows else None,
        efi_params=CBT_WINDOWS_PERSISTENT_DEVICE_PARAMS if identity.windows else None,
        generate_unique_name=False,
        restored_data_disks=[(volume_spec.volume_name, pvc) for volume_spec, pvc in data_disks],
    )
    restored_vm.deploy()
    return restored_vm


def _assert_guest_file(vm: VirtualMachineForTests, filename: str, content: str) -> None:
    """Fail when a restored guest file or block device does not contain the expected text."""
    if is_windows_cbt_vm(vm=vm):
        verify_file_in_windows_vm(windows_vm=vm, file_name_with_path=filename, file_content=content)
        return
    if filename.startswith("/dev/"):
        output = _read_linux_guest_bytes(vm=vm, filename=filename)
        assert content in output, f"VM {vm.name} device {filename} missing {content!r}, read {output!r}"
        return
    output = _read_linux_guest_file(vm=vm, filename=filename)
    assert output.strip() == content, f"VM {vm.name} file {filename} is {output.strip()!r}, expected {content!r}"


def _read_linux_guest_file(vm: VirtualMachineForTests, filename: str) -> str:
    """Return the text of a regular file inside a Linux guest."""
    return _run_guest_command(vm=vm, command=f"cat {filename}")


def _read_linux_guest_bytes(vm: VirtualMachineForTests, filename: str) -> str:
    """Return the leading bytes of a Linux block device."""
    return _run_guest_command(
        vm=vm,
        command=f"sudo dd if={filename} bs=1 count={BLOCK_DEVICE_READ_BYTES} status=none",
    )


def _run_guest_command(vm: VirtualMachineForTests, command: str) -> str:
    """Run one shell command in a Linux guest and return its stdout."""
    return "".join(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(command),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
    )


def _run_python_runner_pod(
    *,
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    runner_script_filename: str,
    container_name: str,
    params_env_name: str,
    runner_params: dict[str, Any],
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    wait_timeout: int,
    pod_role: str,
    volume_devices: list[dict[str, Any]] | None = None,
) -> None:
    """Run a one-shot pod whose process is a mounted Python runner."""
    script_mount_path = "/scripts"
    script_volume_name = "runner-script"
    script_config_map_name = f"{pod_name}-script"
    runner_script_content = Path(__file__).with_name(runner_script_filename).read_text(encoding="utf-8")
    with ConfigMap(
        name=script_config_map_name,
        namespace=namespace,
        client=client,
        data={runner_script_filename: runner_script_content},
    ):
        _run_one_shot_pod(
            pod_name=pod_name,
            namespace=namespace,
            client=client,
            container_name=container_name,
            volume_mounts=[
                *volume_mounts,
                {"name": script_volume_name, "mountPath": script_mount_path, "readOnly": True},
            ],
            volume_devices=volume_devices,
            volumes=[
                *volumes,
                {"name": script_volume_name, "configMap": {"name": script_config_map_name}},
            ],
            container_command=["python3", "-u", f"{script_mount_path}/{runner_script_filename}"],
            container_env=[{"name": params_env_name, "value": json.dumps(runner_params)}],
            wait_timeout=wait_timeout,
            pod_role=pod_role,
        )


def _pod_debug_context(client_pod: Pod) -> str:
    """Return phase, conditions, and logs for a pod that did not succeed."""
    client_pod.get()
    container_name = client_pod.instance.spec.containers[0].name
    try:
        pod_logs = client_pod.log(container=container_name)
    except ApiException as log_error:
        pod_logs = f"<unavailable: {log_error}>"
    return (
        f"phase={client_pod.instance.status.phase}\n"
        f"conditions={client_pod.instance.status.get('conditions') or []}\n"
        f"containerStatuses={client_pod.instance.status.get('containerStatuses') or []}\n"
        f"logs:\n{pod_logs}"
    )


def _run_one_shot_pod(
    *,
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    container_name: str,
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    container_command: list[str],
    wait_timeout: int,
    pod_role: str,
    volume_devices: list[dict[str, Any]] | None = None,
    container_env: list[dict[str, str]] | None = None,
) -> None:
    """Run one pod until it succeeds, and include its logs in the failure."""
    container_spec: dict[str, Any] = {
        **POD_CONTAINER_SPEC,
        "name": container_name,
        "image": NET_UTIL_CONTAINER_IMAGE,
        "command": container_command,
        "env": container_env or [],
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
        restart_policy="Never",
    ) as client_pod:
        LOGGER.info(f"Running CBT {pod_role} pod {pod_name} in {namespace}")
        try:
            client_pod.wait_for_status(
                status=Pod.Status.SUCCEEDED,
                timeout=wait_timeout,
                stop_status=Pod.Status.FAILED,
                sleep=TIMEOUT_5SEC,
            )
        except TimeoutExpiredError as wait_error:
            raise RuntimeError(
                f"CBT {pod_role} pod {client_pod.name} did not succeed: {wait_error}. "
                f"{_pod_debug_context(client_pod=client_pod)}"
            ) from wait_error
        LOGGER.info(f"CBT {pod_role} pod {client_pod.name} completed successfully")
