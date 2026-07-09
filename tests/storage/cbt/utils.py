"""
CBT (Changed Block Tracking) test utilities.

Helper classes and constants for CBT backup and restore testing.
"""

import hashlib
import json
import logging
import re
import shlex
from pathlib import Path
from typing import Any

from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.utils.quantity import parse_quantity
from ocp_resources.config_map import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError

from tests.storage.cbt.pull_collect_runner import PULL_COLLECT_PARAMS_ENV
from tests.storage.cbt.pull_restore_runner import PULL_RESTORE_PARAMS_ENV
from tests.storage.cbt.push_restore_runner import PUSH_RESTORE_PARAMS_ENV
from utilities.constants import (
    NET_UTIL_CONTAINER_IMAGE,
    POD_CONTAINER_SPEC,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_30MIN,
)
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_INCREMENTAL_TEST_DATA: str = "cbt-incremental-backup-test-data"
CBT_BOOT_DISK_TEST_DATA_FILE = "/tmp/cbt-test-data.txt"
CBT_INCREMENTAL_TEST_DATA_FILE = "/tmp/cbt-incremental-test-data.txt"
CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}

BACKUP_DIR = "/backup"
BOOT_VOLUME_MOUNT_KEY = "target-boot"
BOOT_VOLUME_MOUNT_PATH = "/target-vol-0"
BOOT_VOLUME_DEVICE_PATH = "/dev/target-boot"
BACKUP_PVC_VOLUME_KEY = "backup-src"
RESTORE_WORK_VOLUME_KEY = "restore-work"
RESTORE_WORK_MOUNT_PATH = "/work"
CHECKPOINT_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")

PULL_CA_CERT_PATH = "/tmp/backup-ca.crt"
PULL_MAP_SCAN_LIMIT_BYTES = 1 << 30
PULL_COLLECT_CHUNK_SIZE_BYTES = 256 * 1024 * 1024
PULL_MAP_HOLE_DESCRIPTIONS = ["hole", "zero"]
PULL_FULL_BACKUP_MIN_COLLECTED_BYTES = 100 * 1024 * 1024


def cbt_pvc_size_with_headroom(
    source_disk_size: str,
    headroom_gib: int = 10,
    backup_copies: int = 1,
) -> str:
    """Return a PVC size with headroom above the source disk capacity.

    ``backup_copies`` is the number of full-sized backup images the PVC must
    hold (e.g. pull-mode incremental collection seeds a new raw file by copying
    the previous checkpoint).
    """
    source_gib = parse_quantity(source_disk_size) // (1024**3)
    return f"{source_gib * backup_copies + headroom_gib}Gi"


def cbt_resource_id(name: str) -> str:
    """Return a short stable identifier for CBT pods and PVCs."""
    return hashlib.sha256(name.encode()).hexdigest()[:10]


def vm_restore_spec(vm: VirtualMachineForTests) -> dict[str, str]:
    """Return restore identity fields from the VM before deletion.

    Captures instancetype, preference, and os_flavor in one place so callers can
    safely delete the original VM immediately afterward.
    """
    return {
        "vm_instance_type_name": vm.instance.spec["instancetype"]["name"],
        "vm_preference_name": vm.instance.spec["preference"]["name"],
        "os_flavor": vm.os_flavor,
    }


def capture_restore_spec_and_delete_vm(vm: VirtualMachineForTests) -> dict[str, str]:
    """Capture restore identity fields, then delete the original VM.

    Returns:
        dict[str, str]: Fields suitable for spreading into restore helpers
    """
    restore_spec = vm_restore_spec(vm=vm)
    vm.delete(wait=True)
    vm.teardown = False
    return restore_spec


def included_boot_volume(backup: VirtualMachineBackup) -> dict[str, Any]:
    """
    Return the single included boot volume entry from backup status.

    Restore supports one boot disk only. The returned dict always includes
    ``volumeName``.
    """
    included_volumes = backup.instance.status.get("includedVolumes", [])
    if not included_volumes:
        raise RuntimeError(f"Backup {backup.name} has no includedVolumes in status")
    if len(included_volumes) != 1:
        raise RuntimeError(
            f"Backup {backup.name} includes {len(included_volumes)} volumes; boot-disk-only restore supports one volume"
        )
    volume_status = included_volumes[0]
    volume_name = volume_status.get("volumeName", volume_status.get("name"))
    if not volume_name:
        raise RuntimeError(f"Included volume has no volumeName: {volume_status}")
    return {**volume_status, "volumeName": str(volume_name)}


def pull_checkpoint_dir_name(checkpoint_name: str) -> str:
    """Return a checkpoint directory name that sorts in backup order on client storage."""
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", checkpoint_name)
    if iso_match:
        date_part, hour, minute, second = iso_match.groups()
        return f"{date_part}_{hour}-{minute}-{second}"
    timestamp_match = CHECKPOINT_TIMESTAMP_PATTERN.search(string=checkpoint_name)
    if timestamp_match:
        return timestamp_match.group(1)
    return re.sub(r"[^\w.\-]", "_", checkpoint_name)


def build_pull_collect_params(
    *,
    endpoint_cert: str,
    export_token: str,
    map_endpoint: str,
    data_endpoint: str,
    disk_size_bytes: int,
    raw_file: str,
    force_full_backup: bool,
) -> dict[str, Any]:
    """Build JSON-serializable parameters for the pull collect runner pod."""
    return {
        "endpoint_cert": endpoint_cert,
        "export_token": export_token,
        "map_endpoint": map_endpoint,
        "data_endpoint": data_endpoint,
        "disk_size_bytes": disk_size_bytes,
        "raw_file": raw_file,
        "force_full_backup": force_full_backup,
        "pull_ca_cert_path": PULL_CA_CERT_PATH,
        "backup_dir": BACKUP_DIR,
        "pull_map_scan_limit_bytes": PULL_MAP_SCAN_LIMIT_BYTES,
        "pull_collect_chunk_size_bytes": PULL_COLLECT_CHUNK_SIZE_BYTES,
        "pull_map_hole_descriptions": PULL_MAP_HOLE_DESCRIPTIONS,
        "pull_full_backup_min_collected_bytes": PULL_FULL_BACKUP_MIN_COLLECTED_BYTES,
        "checkpoint_timestamp_pattern": CHECKPOINT_TIMESTAMP_PATTERN.pattern,
    }


def pull_collect_params_for_backup(
    *,
    backup: VirtualMachineBackup,
    export_token: str,
    boot_disk_size: str,
) -> dict[str, Any]:
    """
    Build pull collect runner parameters from a ready pull-mode backup.

    Validates export endpoints and checkpoint fields on the backup status before
    building JSON-serializable collect parameters.
    """
    included_volume = included_boot_volume(backup=backup)
    volume_name = included_volume["volumeName"]
    map_endpoint = included_volume.get("mapEndpoint")
    data_endpoint = included_volume.get("dataEndpoint")
    endpoint_cert = backup.instance.status.get("endpointCert")
    if not endpoint_cert:
        raise RuntimeError(f"Backup {backup.name} status has no endpointCert")
    if not map_endpoint:
        raise RuntimeError(f"Backup {backup.name} volume {volume_name} has no mapEndpoint")
    if not data_endpoint:
        raise RuntimeError(f"Backup {backup.name} volume {volume_name} has no dataEndpoint")
    raw_file = (
        f"{BACKUP_DIR}/{volume_name}/"
        f"{pull_checkpoint_dir_name(checkpoint_name=backup.instance.status['checkpointName'])}/"
        f"{volume_name}.raw"
    )
    return build_pull_collect_params(
        endpoint_cert=endpoint_cert,
        export_token=export_token,
        map_endpoint=map_endpoint,
        data_endpoint=data_endpoint,
        disk_size_bytes=int(parse_quantity(boot_disk_size)),
        raw_file=raw_file,
        force_full_backup=bool(backup.instance.spec.get("forceFullBackup", False)),
    )


def build_push_restore_params(*, volume_name: str, target_file: str) -> dict[str, Any]:
    """Build JSON-serializable parameters for the push restore runner pod."""
    return {
        "backup_dir": BACKUP_DIR,
        "volume_work_dir": f"{RESTORE_WORK_MOUNT_PATH}/{volume_name}",
        "target_file": target_file,
        "checkpoint_timestamp_pattern": CHECKPOINT_TIMESTAMP_PATTERN.pattern,
    }


def build_pull_restore_params(
    *,
    volume_name: str,
    target_file: str,
    volume_mode: str,
) -> dict[str, Any]:
    """Build JSON-serializable parameters for the pull restore runner pod."""
    return {
        "backup_dir": BACKUP_DIR,
        "volume_name": volume_name,
        "target_file": target_file,
        "volume_mode": volume_mode,
        "checkpoint_timestamp_pattern": CHECKPOINT_TIMESTAMP_PATTERN.pattern,
    }


def cbt_storage_class_suffix(storage_class_name: str) -> str:
    """Return a short stable suffix for CBT resource names derived from a storage class."""
    return hashlib.sha256(storage_class_name.encode()).hexdigest()[:8]


def assert_restored_vm_has_boot_test_data(vm: VirtualMachineForTests) -> None:
    """Assert the restored VM contains the original boot-disk test data."""
    actual = "".join(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"sudo cat {CBT_BOOT_DISK_TEST_DATA_FILE}"),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
    ).strip()
    assert actual == CBT_TEST_DATA, f"Boot-disk test data mismatch on VM {vm.name}"


def assert_restored_vm_has_boot_and_incremental_test_data(vm: VirtualMachineForTests) -> None:
    """Assert the restored VM contains both full-backup and incremental test data."""
    boot_data = "".join(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"sudo cat {CBT_BOOT_DISK_TEST_DATA_FILE}"),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
    ).strip()
    incremental_data = "".join(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"sudo cat {CBT_INCREMENTAL_TEST_DATA_FILE}"),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
    ).strip()
    assert (boot_data, incremental_data) == (CBT_TEST_DATA, CBT_INCREMENTAL_TEST_DATA), (
        f"Test data mismatch on VM {vm.name}: boot={boot_data!r}, incremental={incremental_data!r}"
    )


def _boot_volume_pod_volumes(
    *, boot_pvc_name: str, volume_mode: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (volume_mounts, volume_devices, volumes) for the restore target boot PVC.

    Block-mode PVCs must be exposed as raw block devices via volumeDevices; filesystem
    mounts (volumeMounts) only work for Filesystem-mode PVCs.
    """
    volumes = [{"name": BOOT_VOLUME_MOUNT_KEY, "persistentVolumeClaim": {"claimName": boot_pvc_name}}]
    if volume_mode == DataVolume.VolumeMode.BLOCK:
        return [], [{"name": BOOT_VOLUME_MOUNT_KEY, "devicePath": BOOT_VOLUME_DEVICE_PATH}], volumes
    return [{"name": BOOT_VOLUME_MOUNT_KEY, "mountPath": BOOT_VOLUME_MOUNT_PATH}], [], volumes


def _restore_target_path(*, volume_mode: str) -> str:
    """Return the in-pod path for the restored boot disk (block device or disk.img)."""
    if volume_mode == DataVolume.VolumeMode.BLOCK:
        return BOOT_VOLUME_DEVICE_PATH
    return f"{BOOT_VOLUME_MOUNT_PATH}/disk.img"


def _deploy_restored_vm_from_pvc(
    *,
    restored_vm_name: str,
    namespace: str,
    client: DynamicClient,
    boot_pvc: PersistentVolumeClaim,
    os_flavor: str,
    vm_preference_name: str,
    vm_instance_type_name: str,
) -> VirtualMachineForTests:
    """Deploy a restored VM attached to the restored boot PVC."""
    restored_vm = VirtualMachineForTests(
        name=restored_vm_name,
        namespace=namespace,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=vm_instance_type_name),
        vm_preference=VirtualMachineClusterPreference(client=client, name=vm_preference_name),
        pvc=boot_pvc,
        os_flavor=os_flavor,
        label=CBT_ENABLED_LABEL,
        generate_unique_name=False,
    )
    restored_vm.deploy()
    return restored_vm


def collect_pull_mode_backup_to_pvc(
    *,
    backup: VirtualMachineBackup,
    client_backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
    collect_pod_name: str,
    collect_params: dict[str, Any],
) -> str:
    """
    Pull backup data from export endpoints into client storage, then delete the backup CR.

    Mimics backup-vendor client behavior from the VEP: pull while ExportReady, store
    offline, then delete VirtualMachineBackup to complete the backup job.

    Args:
        backup: ExportReady pull-mode VirtualMachineBackup CR
        client_backup_pvc_name: PVC where the client stores pulled backup data
        namespace: Namespace for the collector pod
        client: Client for the collector pod and backup CR deletion
        collect_pod_name: Name for the one-shot pull collect pod
        collect_params: JSON-serializable parameters for the pull collect runner

    Returns:
        str: Name of the client PVC containing offline pull backup data
    """
    volume_mounts = [{"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR}]
    volumes = [
        {
            "name": BACKUP_PVC_VOLUME_KEY,
            "persistentVolumeClaim": {"claimName": client_backup_pvc_name},
        }
    ]
    _run_python_runner_pod(
        pod_name=collect_pod_name,
        namespace=namespace,
        client=client,
        runner_script_filename="pull_collect_runner.py",
        container_name="cbt-pull-collect",
        params_env_name=PULL_COLLECT_PARAMS_ENV,
        runner_params=collect_params,
        volume_mounts=volume_mounts,
        volumes=volumes,
        wait_timeout=TIMEOUT_30MIN,
        pod_role="pull collect",
    )

    LOGGER.info(f"Pull backup collection complete for {backup.name}; deleting backup CR")
    backup.delete(wait=True)
    backup.teardown = False
    return client_backup_pvc_name


def restore_vm_from_push_backup(
    *,
    restored_vm_name: str,
    namespace: str,
    client: DynamicClient,
    storage_class: str,
    size: str,
    volume_mode: str,
    access_mode: str,
    backup_pvc_name: str,
    boot_volume_name: str,
    os_flavor: str,
    vm_preference_name: str,
    vm_instance_type_name: str,
) -> VirtualMachineForTests:
    """
    Restore boot disk from QCOW2 incremental chain on push-mode backup PVC.

    Uses qemu-img rebase + convert per VEP restore process. The backup PVC contains
    QCOW2 files (full + incrementals) that are rebased in chronological order and
    converted to a raw disk image.

    Args:
        restored_vm_name: Name for the restored VM
        namespace: Target namespace
        client: Client for VM, PVC, and restore processor pod creation
        storage_class: Storage class for restored disk PVC
        size: Boot disk PVC size
        volume_mode: Boot disk PVC volume mode (mirrors the original VM's disk)
        access_mode: Boot disk PVC access mode (mirrors the original VM's disk)
        backup_pvc_name: Push-mode backup PVC containing QCOW2 files
        boot_volume_name: Original boot volume name from backup metadata
        os_flavor: OS flavor for the restored VM
        vm_preference_name: Cluster preference name for the restored VM
        vm_instance_type_name: Cluster instancetype name for the restored VM

    Returns:
        VirtualMachineForTests: Deployed restored VM (not started)
    """
    restore_id = cbt_resource_id(name=restored_vm_name)
    LOGGER.info(f"CBT push restore {restored_vm_name}: boot_volume_name={boot_volume_name}")

    with PersistentVolumeClaim(
        name=f"cbt-rst-{restore_id}-boot",
        namespace=namespace,
        client=client,
        accessmodes=access_mode,
        size=size,
        storage_class=storage_class,
        volume_mode=volume_mode,
        teardown=False,
    ) as boot_pvc:
        boot_volume_mounts, boot_volume_devices, boot_volumes = _boot_volume_pod_volumes(
            boot_pvc_name=boot_pvc.name, volume_mode=volume_mode
        )
        target_file = _restore_target_path(volume_mode=volume_mode)
        volume_mounts = [
            *boot_volume_mounts,
            {"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR, "readOnly": True},
            {"name": RESTORE_WORK_VOLUME_KEY, "mountPath": RESTORE_WORK_MOUNT_PATH},
        ]
        volumes = [
            *boot_volumes,
            {"name": BACKUP_PVC_VOLUME_KEY, "persistentVolumeClaim": {"claimName": backup_pvc_name}},
            {"name": RESTORE_WORK_VOLUME_KEY, "emptyDir": {}},
        ]
        _run_python_runner_pod(
            pod_name=f"cbt-rstr-{restore_id}-push",
            namespace=namespace,
            client=client,
            runner_script_filename="push_restore_runner.py",
            container_name="cbt-push-restore",
            params_env_name=PUSH_RESTORE_PARAMS_ENV,
            runner_params=build_push_restore_params(
                volume_name=boot_volume_name,
                target_file=target_file,
            ),
            volume_mounts=volume_mounts,
            volume_devices=boot_volume_devices or None,
            volumes=volumes,
            wait_timeout=TIMEOUT_30MIN,
            pod_role="push restore",
        )
        return _deploy_restored_vm_from_pvc(
            restored_vm_name=restored_vm_name,
            namespace=namespace,
            client=client,
            boot_pvc=boot_pvc,
            os_flavor=os_flavor,
            vm_preference_name=vm_preference_name,
            vm_instance_type_name=vm_instance_type_name,
        )


def restore_vm_from_pull_client_backup(
    *,
    restored_vm_name: str,
    namespace: str,
    client: DynamicClient,
    storage_class: str,
    size: str,
    volume_mode: str,
    access_mode: str,
    client_backup_pvc_name: str,
    boot_volume_name: str,
    os_flavor: str,
    vm_preference_name: str,
    vm_instance_type_name: str,
) -> VirtualMachineForTests:
    """
    Restore boot disk from raw snapshot on pull-mode client backup PVC.

    Pull clients store complete raw snapshots; no rebasing needed. When multiple
    snapshots exist, restores from the latest checkpoint for the boot volume only.

    Args:
        restored_vm_name: Name for the restored VM
        namespace: Target namespace
        client: Client for VM, PVC, and restore processor pod creation
        storage_class: Storage class for restored disk PVC
        size: Boot disk PVC size
        volume_mode: Boot disk PVC volume mode (mirrors the original VM's disk)
        access_mode: Boot disk PVC access mode (mirrors the original VM's disk)
        client_backup_pvc_name: Pull-mode client backup PVC containing raw snapshots
        boot_volume_name: Original boot volume name used under client backup storage
        os_flavor: OS flavor for the restored VM
        vm_preference_name: Cluster preference name for the restored VM
        vm_instance_type_name: Cluster instancetype name for the restored VM

    Returns:
        VirtualMachineForTests: Deployed restored VM (not started)
    """
    restore_id = cbt_resource_id(name=restored_vm_name)
    LOGGER.info(f"CBT pull client restore {restored_vm_name}: boot_volume_name={boot_volume_name}")

    with PersistentVolumeClaim(
        name=f"cbt-rst-{restore_id}-boot",
        namespace=namespace,
        client=client,
        accessmodes=access_mode,
        size=size,
        storage_class=storage_class,
        volume_mode=volume_mode,
        teardown=False,
    ) as boot_pvc:
        boot_volume_mounts, boot_volume_devices, boot_volumes = _boot_volume_pod_volumes(
            boot_pvc_name=boot_pvc.name, volume_mode=volume_mode
        )
        target_file = _restore_target_path(volume_mode=volume_mode)
        volume_mounts = [
            *boot_volume_mounts,
            {"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR, "readOnly": True},
        ]
        volumes = [
            *boot_volumes,
            {"name": BACKUP_PVC_VOLUME_KEY, "persistentVolumeClaim": {"claimName": client_backup_pvc_name}},
        ]
        _run_python_runner_pod(
            pod_name=f"cbt-rstr-{restore_id}-client",
            namespace=namespace,
            client=client,
            runner_script_filename="pull_restore_runner.py",
            container_name="cbt-pull-restore",
            params_env_name=PULL_RESTORE_PARAMS_ENV,
            runner_params=build_pull_restore_params(
                volume_name=boot_volume_name,
                target_file=target_file,
                volume_mode=volume_mode,
            ),
            volume_mounts=volume_mounts,
            volume_devices=boot_volume_devices or None,
            volumes=volumes,
            wait_timeout=TIMEOUT_30MIN,
            pod_role="pull client restore",
        )
        return _deploy_restored_vm_from_pvc(
            restored_vm_name=restored_vm_name,
            namespace=namespace,
            client=client,
            boot_pvc=boot_pvc,
            os_flavor=os_flavor,
            vm_preference_name=vm_preference_name,
            vm_instance_type_name=vm_instance_type_name,
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
    """Run a one-shot pod whose main process executes a mounted Python runner script."""
    script_mount_path = "/scripts"
    script_volume_key = "runner-script"
    script_config_map_name = f"{pod_name}-script"
    runner_script_content = Path(__file__).with_name(runner_script_filename).read_text(encoding="utf-8")
    runner_pod_volume_mounts = [
        *volume_mounts,
        {
            "name": script_volume_key,
            "mountPath": script_mount_path,
            "readOnly": True,
        },
    ]
    runner_pod_volumes = [
        *volumes,
        {
            "name": script_volume_key,
            "configMap": {"name": script_config_map_name},
        },
    ]
    with ConfigMap(
        name=script_config_map_name,
        namespace=namespace,
        client=client,
        data={runner_script_filename: runner_script_content},
    ):
        _run_one_shot_client_pod(
            pod_name=pod_name,
            namespace=namespace,
            client=client,
            container_name=container_name,
            volume_mounts=runner_pod_volume_mounts,
            volume_devices=volume_devices,
            volumes=runner_pod_volumes,
            container_command=[
                "python3",
                "-u",
                f"{script_mount_path}/{runner_script_filename}",
            ],
            container_env=[
                {
                    "name": params_env_name,
                    "value": json.dumps(runner_params),
                }
            ],
            wait_timeout=wait_timeout,
            pod_role=pod_role,
        )


def _pod_debug_context(client_pod: Pod) -> str:
    """Return pod phase, container state, and logs for failure diagnostics."""
    client_pod.get()
    container_name = client_pod.instance.spec.containers[0].name
    container_statuses = client_pod.instance.status.get("containerStatuses") or []
    pod_conditions = client_pod.instance.status.get("conditions") or []
    try:
        pod_logs = client_pod.log(container=container_name)
    except ApiException as log_error:
        pod_logs = f"<unavailable: {log_error}>"
    return (
        f"phase={client_pod.instance.status.phase}\n"
        f"conditions={pod_conditions}\n"
        f"containerStatuses={container_statuses}\n"
        f"logs:\n{pod_logs}"
    )


def _run_one_shot_client_pod(
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
    """Run a single-purpose client pod whose main process runs to completion."""
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
