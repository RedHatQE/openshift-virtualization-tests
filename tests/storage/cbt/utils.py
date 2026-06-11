"""
CBT (Changed Block Tracking) test utilities.

Helper classes and constants for CBT backup and restore testing.
"""

import base64
import hashlib
import logging
import os
import re
import shlex
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands

from utilities.constants import (
    NET_UTIL_CONTAINER_IMAGE,
    OS_FLAVOR_RHEL,
    POD_CONTAINER_SPEC,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
    U1_SMALL,
)
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from ocp_resources.virtual_machine import VirtualMachine

LOGGER = logging.getLogger(__name__)

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_INCREMENTAL_TEST_DATA: str = "cbt-incremental-backup-test-data"

CBT_BOOT_DISK_TEST_DATA_FILE = "/tmp/cbt-test-data.txt"
CBT_INCREMENTAL_TEST_DATA_FILE = "/tmp/cbt-incremental-test-data.txt"

CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}

RESTORED_DISK_FILENAME = "disk.img"
DEFAULT_BACKUP_VOLUME_NAME = "boot"
K8S_NAME_MAX_LENGTH = 63
BACKUP_PVC_VOLUME_KEY = "backup-src"
RESTORE_WORK_VOLUME_KEY = "restore-work"
RESTORE_WORK_MOUNT_PATH = "/work"
BACKUP_DIR = "/backup"
PULL_CA_CERT_PATH = "/tmp/backup-ca.crt"
PULL_CHUNK_PATH = "/tmp/pull-chunk"
RESTORE_PROCESSOR_CONTAINER = "cbt-restore-processor"
PULL_RESTORE_CHUNK_SIZE_BYTES = 64 * 1024 * 1024
PULL_RESTORE_PVC_SIZE_OVERHEAD = "2Gi"
PULL_RESTORE_POD_TIMEOUT_SECONDS = TIMEOUT_30MIN
CHECKPOINT_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


def vm_boot_disk_size(vm: VirtualMachine) -> str:
    """Return the boot disk storage request from a VM data volume template."""
    return vm.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]


def cbt_pvc_size_with_headroom(source_disk_size: str, headroom_gib: int = 10) -> str:
    """Return a PVC size with headroom above the source disk capacity."""
    return f"{parse_quantity(source_disk_size) // (1024**3) + headroom_gib}Gi"


def _uses_placeholder_qcow2_suffixes(qcow2_suffixes: list[str]) -> bool:
    return any(
        qcow2_suffix == DEFAULT_BACKUP_VOLUME_NAME or qcow2_suffix.startswith("volume-")
        for qcow2_suffix in qcow2_suffixes
    )


def cbt_restore_resource_id(restored_vm_name: str) -> str:
    """Return a short stable identifier for restore pods and PVCs."""
    return hashlib.sha256(restored_vm_name.encode()).hexdigest()[:10]


def truncate_k8s_name(name: str, max_length: int = K8S_NAME_MAX_LENGTH) -> str:
    """Truncate a Kubernetes resource name to the DNS label limit."""
    if len(name) <= max_length:
        return name
    return name[:max_length].rstrip("-")


def _target_pvc_name(restore_id: str, volume_index: int) -> str:
    suffix = "boot" if volume_index == 0 else f"vol{volume_index}"
    return truncate_k8s_name(name=f"cbt-rst-{restore_id}-{suffix}")


def _target_volume_mount_key(volume_index: int) -> str:
    return "target-boot" if volume_index == 0 else f"target-vol-{volume_index}"


def _target_mount_path(volume_index: int) -> str:
    return f"/target-vol-{volume_index}"


def read_file_content_from_vm(vm: VirtualMachineForTests, file_path: str) -> str:
    """
    Read a text file from a Linux VM over SSH.

    Args:
        vm: Running VM with SSH access
        file_path: Absolute path to the file inside the guest

    Returns:
        str: File content with surrounding whitespace stripped
    """
    result = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"cat {file_path}"),
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    return "".join(result).strip()


def add_pvc_volume_to_vm(
    vm: VirtualMachineForTests,
    pvc: PersistentVolumeClaim,
    volume_name: str,
) -> None:
    """
    Attach an existing PVC as an additional virtio disk to a VM.

    Args:
        vm: VirtualMachine to patch
        pvc: Bound PVC to attach
        volume_name: Volume and disk entry name in the VM spec
    """
    vm_instance = vm.instance.to_dict()
    template_spec = vm_instance["spec"]["template"]["spec"]
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "domain": {
                        "devices": {
                            "disks": [
                                *template_spec["domain"]["devices"]["disks"],
                                {"disk": {"bus": "virtio"}, "name": volume_name},
                            ]
                        }
                    },
                    "volumes": [
                        *template_spec["volumes"],
                        {"name": volume_name, "persistentVolumeClaim": {"claimName": pvc.name}},
                    ],
                },
            },
        }
    }
    ResourceEditor(patches={vm: patch}).update()


@contextmanager
def running_restored_vm_from_backup(
    *,
    backup: VirtualMachineBackup,
    source_vm: VirtualMachine,
    restored_vm_name: str,
    namespace: str,
    client: Any,
    admin_client: Any,
    storage_class: str,
    backup_pvc_name: str | None = None,
    delete_source_vm_before_restore: bool = True,
) -> Iterator[VirtualMachineForTests]:
    """
    Restore a VM from backup, start it, and delete it on teardown.

    Push-mode restores delete the source VM before materializing disks. Pull-mode
    restores delete the source VM after restore because the export may still reference it.
    """
    source_disk_size = vm_boot_disk_size(vm=source_vm)
    if delete_source_vm_before_restore:
        source_vm.delete(wait=True)

    restored_vm = restore_vm_from_backup(
        backup=backup,
        restored_vm_name=restored_vm_name,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc_name,
    )

    if not delete_source_vm_before_restore:
        source_vm.delete(wait=True)

    running_vm(vm=restored_vm)
    try:
        yield restored_vm
    finally:
        restored_vm.delete(wait=True)


def restore_vm_from_backup(
    backup: VirtualMachineBackup,
    restored_vm_name: str,
    namespace: str,
    client: Any,
    storage_class: str,
    size: str,
    admin_client: Any,
    backup_pvc_name: str | None = None,
    data_disk_size: str | None = None,
    source_volume_names: list[str] | None = None,
    os_flavor: str = OS_FLAVOR_RHEL,
    vm_preference_name: str = "rhel.9",
    vm_instance_type_name: str = U1_SMALL,
) -> VirtualMachine:
    """
    Restore VM disk(s) from a completed CBT backup and create a new VM.

    Args:
        backup: Completed VirtualMachineBackup CR
        restored_vm_name: Name for the restored VM
        namespace: Target namespace
        client: Client for VM and PVC creation
        storage_class: Storage class for restored disk PVCs
        size: Boot disk PVC size
        admin_client: Privileged client for restore processor pods
        backup_pvc_name: Push-mode backup output PVC; defaults to spec.pvcName
        data_disk_size: Optional data disk PVC size for multi-disk restores
        source_volume_names: VM template volume names when backup status omits them
        os_flavor: OS flavor for the restored VM
        vm_preference_name: Cluster preference name for the restored VM
        vm_instance_type_name: Cluster instancetype name for the restored VM

    Returns:
        VirtualMachine: Deployed restored VM (not started)
    """
    backup_mode = backup.instance.spec["mode"]
    status_volume_names = backup.included_volume_names
    volume_names = backup.resolve_restore_volume_names(source_volume_names=source_volume_names)
    qcow2_suffixes = source_volume_names if source_volume_names else status_volume_names
    LOGGER.info(f"CBT restore {restored_vm_name}: volume_names={volume_names}, qcow2_suffixes={qcow2_suffixes}")
    restore_id = cbt_restore_resource_id(restored_vm_name=restored_vm_name)

    volume_sizes = {volume_names[0]: size}
    if len(volume_names) > 1:
        if data_disk_size is None:
            raise ValueError("data_disk_size is required when backup includes multiple volumes")
        for volume_name in volume_names[1:]:
            volume_sizes[volume_name] = data_disk_size

    with ExitStack() as stack:
        target_pvcs: dict[str, PersistentVolumeClaim] = {}
        volume_mount_targets: list[tuple[str, str]] = []
        for index, volume_name in enumerate(volume_names):
            mount_path = _target_mount_path(volume_index=index)
            volume_mount_targets.append((volume_name, mount_path))
            target_pvc_size = volume_sizes[volume_name]
            if backup_mode == VirtualMachineBackup.Mode.PULL:
                target_pvc_size = _pull_restore_target_pvc_size(source_size=target_pvc_size)
            target_pvcs[volume_name] = stack.enter_context(
                PersistentVolumeClaim(
                    name=_target_pvc_name(restore_id=restore_id, volume_index=index),
                    namespace=namespace,
                    client=client,
                    accessmodes=PersistentVolumeClaim.AccessMode.RWO,
                    size=target_pvc_size,
                    storage_class=storage_class,
                    volume_mode=DataVolume.VolumeMode.FILE,
                    teardown=False,
                )
            )

        volume_mounts: list[dict[str, Any]] = []
        volumes: list[dict[str, Any]] = []

        for index, volume_name in enumerate(volume_names):
            volume_key = _target_volume_mount_key(volume_index=index)
            mount_path = _target_mount_path(volume_index=index)
            volume_mounts.append({"name": volume_key, "mountPath": mount_path})
            volumes.append({
                "name": volume_key,
                "persistentVolumeClaim": {"claimName": target_pvcs[volume_name].name},
            })

        restore_pod_name = truncate_k8s_name(
            name=f"cbt-rstr-{restore_id}-{'push' if backup_mode == VirtualMachineBackup.Mode.PUSH else 'pull'}"
        )

        if backup_mode == VirtualMachineBackup.Mode.PUSH:
            backup_pvc = backup_pvc_name or backup.instance.spec["pvcName"]
            volume_mounts.append({"name": BACKUP_PVC_VOLUME_KEY, "mountPath": "/backup", "readOnly": True})
            volumes.append({
                "name": BACKUP_PVC_VOLUME_KEY,
                "persistentVolumeClaim": {"claimName": backup_pvc},
            })
            volume_mounts.append({"name": RESTORE_WORK_VOLUME_KEY, "mountPath": RESTORE_WORK_MOUNT_PATH})
            volumes.append({"name": RESTORE_WORK_VOLUME_KEY, "emptyDir": {}})
            _run_restore_processor_pod(
                pod_name=restore_pod_name,
                namespace=namespace,
                admin_client=admin_client,
                volume_mounts=volume_mounts,
                volumes=volumes,
                wait_timeout=TIMEOUT_10MIN,
                restore_action=lambda restore_pod: _run_push_restore(
                    restore_pod=restore_pod,
                    volume_mount_targets=volume_mount_targets,
                    qcow2_suffixes=qcow2_suffixes,
                ),
            )
        elif backup_mode == VirtualMachineBackup.Mode.PULL:
            _run_restore_processor_pod(
                pod_name=restore_pod_name,
                namespace=namespace,
                admin_client=admin_client,
                volume_mounts=volume_mounts,
                volumes=volumes,
                wait_timeout=PULL_RESTORE_POD_TIMEOUT_SECONDS,
                restore_action=lambda restore_pod: _run_pull_restore(
                    restore_pod=restore_pod,
                    backup=backup,
                    volume_mount_targets=volume_mount_targets,
                    volume_sizes=volume_sizes,
                ),
            )
        else:
            raise ValueError(f"Unsupported backup mode {backup_mode!r}; expected Push or Pull")

        boot_volume_name = volume_names[0]
        restored_vm = VirtualMachineForTests(
            name=restored_vm_name,
            namespace=namespace,
            client=client,
            vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=vm_instance_type_name),
            vm_preference=VirtualMachineClusterPreference(client=client, name=vm_preference_name),
            pvc=target_pvcs[boot_volume_name],
            os_flavor=os_flavor,
            label=CBT_ENABLED_LABEL,
            generate_unique_name=False,
        )
        restored_vm.deploy()

        for volume_name in volume_names[1:]:
            add_pvc_volume_to_vm(
                vm=restored_vm,
                pvc=target_pvcs[volume_name],
                volume_name=volume_name,
            )

        return restored_vm


def _checkpoint_timestamp_from_qcow2_path(qcow2_path: str) -> str:
    """Return the checkpoint timestamp embedded in a backup qcow2 path."""
    match = CHECKPOINT_TIMESTAMP_PATTERN.search(qcow2_path)
    return match.group(1) if match else ""


def _sort_qcow2_files_by_checkpoint(qcow2_files: list[str]) -> list[str]:
    """Return qcow2 files sorted by checkpoint timestamp in backup path order."""
    return sorted(qcow2_files, key=_checkpoint_timestamp_from_qcow2_path)


def _latest_checkpoint_timestamp(qcow2_files: list[str]) -> str:
    """Return the newest checkpoint timestamp found across qcow2 backup paths."""
    checkpoint_timestamps = [
        timestamp
        for timestamp in (_checkpoint_timestamp_from_qcow2_path(path=path) for path in qcow2_files)
        if timestamp
    ]
    if not checkpoint_timestamps:
        raise RuntimeError(f"No checkpoint timestamps found in qcow2 paths: {qcow2_files}")
    return sorted(checkpoint_timestamps)[-1]


def _pod_execute(restore_pod: Pod, command: list[str], timeout: int = TIMEOUT_10MIN) -> str:
    """Run a command in the restore processor pod."""
    LOGGER.info(f"CBT restore exec on {restore_pod.name}: {command}")
    return restore_pod.execute(
        command=command,
        timeout=timeout,
        container=RESTORE_PROCESSOR_CONTAINER,
    )


def _write_file_in_pod(restore_pod: Pod, file_path: str, content: str) -> None:
    """Write a text file inside the restore processor pod."""
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
    _pod_execute(
        restore_pod=restore_pod,
        command=[
            "/bin/bash",
            "-c",
            f"echo {shlex.quote(encoded_content)} | base64 -d > {shlex.quote(file_path)}",
        ],
    )


def _list_qcow2_files_in_backup(restore_pod: Pod, name_pattern: str) -> list[str]:
    """List qcow2 files under the mounted backup PVC matching a glob pattern."""
    find_output = _pod_execute(
        restore_pod=restore_pod,
        command=["/usr/bin/find", BACKUP_DIR, "-name", name_pattern, "-type", "f"],
    )
    qcow2_files = [line.strip() for line in find_output.splitlines() if line.strip()]
    if qcow2_files:
        return qcow2_files
    backup_listing = _pod_execute(
        restore_pod=restore_pod,
        command=["/usr/bin/find", BACKUP_DIR, "-type", "f"],
    )
    raise RuntimeError(
        f"No qcow2 files matching {name_pattern!r} under {BACKUP_DIR}. Files:\n{backup_listing}"
    )


def _qemu_img_convert_to_raw(restore_pod: Pod, qcow2_file: str, target_dir: str) -> None:
    """Convert a qcow2 backup image to a raw disk file on the target PVC mount."""
    target_file = f"{target_dir}/{RESTORED_DISK_FILENAME}"
    _pod_execute(
        restore_pod=restore_pod,
        command=["qemu-img", "convert", "-f", "qcow2", "-O", "raw", qcow2_file, target_file],
        timeout=PULL_RESTORE_POD_TIMEOUT_SECONDS,
    )


def _restore_push_volume_chain(
    restore_pod: Pod,
    volume_name: str,
    target_dir: str,
    qcow2_suffix: str,
    single_volume: bool,
) -> None:
    """
    Restore one backed-up volume from its qcow2 chain.

    Incremental chains copy qcow2 files to a writable work dir, rebase in checkpoint
    order, then convert. Incremental images reference absolute virt-launcher backing
    paths that are not available on the read-only backup PVC mount.
    """
    name_pattern = "*.qcow2" if single_volume else f"*-{qcow2_suffix}.qcow2"
    qcow2_files = _sort_qcow2_files_by_checkpoint(
        _list_qcow2_files_in_backup(restore_pod=restore_pod, name_pattern=name_pattern)
    )
    if len(qcow2_files) == 1:
        _qemu_img_convert_to_raw(restore_pod=restore_pod, qcow2_file=qcow2_files[0], target_dir=target_dir)
        return

    volume_work_dir = f"{RESTORE_WORK_MOUNT_PATH}/{volume_name}"
    _pod_execute(restore_pod=restore_pod, command=["/bin/mkdir", "-p", volume_work_dir])
    work_files: list[str] = []
    for file_index, qcow2_file in enumerate(qcow2_files):
        work_path = f"{volume_work_dir}/chain-{file_index}-{os.path.basename(qcow2_file)}"
        _pod_execute(restore_pod=restore_pod, command=["/bin/cp", qcow2_file, work_path])
        work_files.append(work_path)

    base_image = work_files[0]
    for work_file in work_files[1:]:
        _pod_execute(
            restore_pod=restore_pod,
            command=["qemu-img", "rebase", "-b", base_image, "-F", "qcow2", "-f", "qcow2", "-u", work_file],
        )
        base_image = work_file
    _qemu_img_convert_to_raw(restore_pod=restore_pod, qcow2_file=base_image, target_dir=target_dir)


def _restore_push_multi_disk_with_placeholder_suffixes(
    restore_pod: Pod,
    volume_mount_targets: list[tuple[str, str]],
    qcow2_suffixes: list[str],
) -> None:
    """Restore multi-disk backups when status volume names are placeholders."""
    all_qcow2_files = _list_qcow2_files_in_backup(restore_pod=restore_pod, name_pattern="*.qcow2")
    latest_timestamp = _latest_checkpoint_timestamp(qcow2_files=all_qcow2_files)
    for (_, target_dir), qcow2_suffix in zip(volume_mount_targets, qcow2_suffixes, strict=True):
        matching_files = [
            path
            for path in all_qcow2_files
            if latest_timestamp in path and path.endswith(f"-{qcow2_suffix}.qcow2")
        ]
        if not matching_files:
            raise RuntimeError(
                f"No qcow2 file found for suffix {qcow2_suffix!r} in checkpoint {latest_timestamp}. "
                f"Files: {all_qcow2_files}"
            )
        _qemu_img_convert_to_raw(restore_pod=restore_pod, qcow2_file=sorted(matching_files)[-1], target_dir=target_dir)


def _run_push_restore(
    restore_pod: Pod,
    volume_mount_targets: list[tuple[str, str]],
    qcow2_suffixes: list[str],
) -> None:
    """Restore all backed-up volumes from a push-mode backup PVC."""
    if len(volume_mount_targets) > 1 and _uses_placeholder_qcow2_suffixes(qcow2_suffixes=qcow2_suffixes):
        _restore_push_multi_disk_with_placeholder_suffixes(
            restore_pod=restore_pod,
            volume_mount_targets=volume_mount_targets,
            qcow2_suffixes=qcow2_suffixes,
        )
        return

    single_volume = len(volume_mount_targets) == 1
    for (volume_name, target_dir), qcow2_suffix in zip(volume_mount_targets, qcow2_suffixes, strict=True):
        _restore_push_volume_chain(
            restore_pod=restore_pod,
            volume_name=volume_name,
            target_dir=target_dir,
            qcow2_suffix=qcow2_suffix,
            single_volume=single_volume,
        )


def _pvc_size_to_bytes(size: str) -> int:
    """Convert a Kubernetes storage quantity string to bytes."""
    return int(parse_quantity(size))


def _pull_restore_target_pvc_size(source_size: str) -> str:
    """
    Return a filesystem PVC size large enough to hold a pulled raw disk image.

    Pull restore writes the full virtual disk size as a raw file; filesystem metadata
    and reserved blocks require headroom beyond the source disk capacity.
    """
    gibibyte = 1024**3
    total_bytes = int(parse_quantity(source_size)) + int(parse_quantity(PULL_RESTORE_PVC_SIZE_OVERHEAD))
    gibibytes = (total_bytes + gibibyte - 1) // gibibyte
    return f"{gibibytes}Gi"


def _get_backup_export_token(backup: VirtualMachineBackup) -> str:
    """Return the pull-mode export token from tokenSecretRef."""
    return backup.get_export_token()


def _download_pull_volume(
    restore_pod: Pod,
    data_endpoint: str,
    export_token: str,
    target_dir: str,
    disk_size_bytes: int,
) -> None:
    """
    Download a full raw volume from a pull-mode data endpoint.

    Pull-mode backup endpoints differ from VMExport manifest URLs: authentication uses the
    x-kubevirt-export-token query parameter and the data endpoint requires length/offset
    query parameters (see kubevirt tests/storage/backup_test.go verifyPullEndpoints).
    """
    target_file = f"{target_dir}/{RESTORED_DISK_FILENAME}"
    _pod_execute(
        restore_pod=restore_pod,
        command=["/bin/bash", "-c", f": > {shlex.quote(target_file)}"],
    )
    offset = 0
    while offset < disk_size_bytes:
        remaining_bytes = disk_size_bytes - offset
        chunk_length = min(PULL_RESTORE_CHUNK_SIZE_BYTES, remaining_bytes)
        download_url = (
            f"{data_endpoint}?x-kubevirt-export-token={export_token}"
            f"&offset={offset}&length={chunk_length}"
        )
        _pod_execute(
            restore_pod=restore_pod,
            command=[
                "curl",
                "-s",
                "-L",
                "--fail",
                "--cacert",
                PULL_CA_CERT_PATH,
                download_url,
                "--output",
                PULL_CHUNK_PATH,
            ],
            timeout=TIMEOUT_10MIN,
        )
        _pod_execute(
            restore_pod=restore_pod,
            command=[
                "dd",
                f"if={PULL_CHUNK_PATH}",
                f"of={target_file}",
                "oflag=seek_bytes",
                f"seek={offset}",
                "conv=notrunc",
                "status=none",
            ],
        )
        offset += chunk_length


def _run_pull_restore(
    restore_pod: Pod,
    backup: VirtualMachineBackup,
    volume_mount_targets: list[tuple[str, str]],
    volume_sizes: dict[str, str],
) -> None:
    """Restore all backed-up volumes from pull-mode export endpoints."""
    included_volumes = backup.instance.status.get("includedVolumes", [])
    endpoint_cert = backup.instance.status.get("endpointCert", "")
    if not endpoint_cert:
        raise RuntimeError(f"Backup {backup.name} status has no endpointCert")

    export_token = _get_backup_export_token(backup=backup)
    _write_file_in_pod(restore_pod=restore_pod, file_path=PULL_CA_CERT_PATH, content=endpoint_cert)

    for volume, (volume_name, target_dir) in zip(included_volumes, volume_mount_targets, strict=True):
        data_endpoint = volume.get("dataEndpoint")
        if not data_endpoint:
            raise RuntimeError(f"Backup {backup.name} volume {volume_name} has no dataEndpoint")
        disk_size_bytes = _pvc_size_to_bytes(size=volume_sizes[volume_name])
        LOGGER.info(f"Pull restore volume {volume_name} from {data_endpoint} ({disk_size_bytes} bytes)")
        _download_pull_volume(
            restore_pod=restore_pod,
            data_endpoint=data_endpoint,
            export_token=export_token,
            target_dir=target_dir,
            disk_size_bytes=disk_size_bytes,
        )


def _run_restore_processor_pod(
    pod_name: str,
    namespace: str,
    admin_client: Any,
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    wait_timeout: int,
    restore_action: Callable[[Pod], None],
) -> None:
    """Run restore commands in a long-lived processor pod."""
    container_spec = {
        **POD_CONTAINER_SPEC,
        "name": RESTORE_PROCESSOR_CONTAINER,
        "image": NET_UTIL_CONTAINER_IMAGE,
        "command": ["sleep", "infinity"],
        "volumeMounts": volume_mounts,
    }

    with Pod(
        name=pod_name,
        namespace=namespace,
        client=admin_client,
        containers=[container_spec],
        volumes=volumes,
        restart_policy="Never",
    ) as restore_pod:
        LOGGER.info(f"Running CBT restore processor pod {pod_name} in {namespace}")
        restore_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=wait_timeout)
        try:
            restore_action(restore_pod)
        except Exception as restore_error:
            pod_logs = restore_pod.log()
            raise RuntimeError(
                f"Restore pod {restore_pod.name} failed during restore: {restore_error}. Logs:\n{pod_logs}"
            ) from restore_error
        LOGGER.info(f"Restore pod {restore_pod.name} completed successfully")
