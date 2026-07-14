"""
CBT (Changed Block Tracking) test utilities.

Helper classes and constants for CBT backup and restore testing.
"""

import hashlib
import json
import logging
import re
import shlex
from collections.abc import Callable, Generator
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
from utilities.constants.networking import NET_UTIL_CONTAINER_IMAGE, POD_CONTAINER_SPEC
from utilities.constants.timeouts import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_30MIN,
)
from utilities.virt import VirtualMachineForTests, running_vm

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


def _short_hash(value: str, length: int) -> str:
    """Return a short stable hex digest of value."""
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def cbt_resource_id(name: str) -> str:
    """Return a short stable identifier for CBT pods and PVCs."""
    return _short_hash(value=name, length=10)


def vm_restore_spec(vm: VirtualMachineForTests) -> dict[str, str]:
    """Return restore identity fields from the VM before deletion."""
    return {
        "vm_instance_type_name": vm.instance.spec["instancetype"]["name"],
        "vm_preference_name": vm.instance.spec["preference"]["name"],
        "os_flavor": vm.os_flavor,
    }


def capture_restore_spec_and_delete_vm(vm: VirtualMachineForTests) -> dict[str, str]:
    """Capture restore identity fields, then delete the original VM."""
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
    return _short_hash(value=storage_class_name, length=8)


def _read_guest_file(vm: VirtualMachineForTests, filename: str) -> str:
    """Return the contents of a file from the guest over SSH."""
    return "".join(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"sudo cat {filename}"),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
    ).strip()


def assert_restored_vm_has_boot_test_data(vm: VirtualMachineForTests) -> None:
    """Assert the restored VM contains the original boot-disk test data."""
    assert _read_guest_file(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE) == CBT_TEST_DATA, (
        f"Boot-disk test data mismatch on VM {vm.name}"
    )


def assert_restored_vm_has_boot_and_incremental_test_data(vm: VirtualMachineForTests) -> None:
    """Assert the restored VM contains both full-backup and incremental test data."""
    assert_restored_vm_has_boot_test_data(vm=vm)
    assert _read_guest_file(vm=vm, filename=CBT_INCREMENTAL_TEST_DATA_FILE) == CBT_INCREMENTAL_TEST_DATA, (
        f"Incremental test data mismatch on VM {vm.name}"
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


def create_and_collect_pull_mode_backup(
    *,
    name: str,
    namespace: str,
    client: DynamicClient,
    token_secret_name: str,
    export_token: str,
    staging_pvc_name: str,
    client_backup_pvc_name: str,
    backup_tracker_source: dict[str, str],
    force_full_backup: bool,
    boot_disk_size: str,
) -> None:
    """Create a pull-mode backup, wait until export is ready, and collect it offline."""
    with VirtualMachineBackup(
        name=name,
        namespace=namespace,
        client=client,
        mode=VirtualMachineBackup.Mode.PULL,
        token_secret_ref=token_secret_name,
        pvc_name=staging_pvc_name,
        force_full_backup=force_full_backup,
        source=backup_tracker_source,
    ) as backup:
        # Pull readiness is Progressing=True with reason ExportReady; there is no
        # condition type named ExportReady.
        backup.wait_for_condition(
            condition="Progressing",
            status=VirtualMachineBackup.Condition.Status.TRUE,
            reason="ExportReady",
            timeout=TIMEOUT_10MIN,
            sleep_time=TIMEOUT_5SEC,
        )
        collect_pull_mode_backup_to_pvc(
            backup=backup,
            client_backup_pvc_name=client_backup_pvc_name,
            namespace=namespace,
            client=client,
            collect_pod_name=f"cbt-pull-collect-{cbt_resource_id(name=f'{backup.name}-collect')}",
            collect_params=pull_collect_params_for_backup(
                backup=backup,
                export_token=export_token,
                boot_disk_size=boot_disk_size,
            ),
        )


def _restore_vm_from_backup_pvc(
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
    runner_script_filename: str,
    container_name: str,
    params_env_name: str,
    runner_params: dict[str, Any],
    pod_name_suffix: str,
    pod_role: str,
    include_restore_work_volume: bool = False,
) -> VirtualMachineForTests:
    """Create a boot PVC, run a restore runner against backup storage, deploy the VM."""
    restore_id = cbt_resource_id(name=restored_vm_name)
    LOGGER.info(f"CBT {pod_role} {restored_vm_name}: boot_volume_name={boot_volume_name}")

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
        volume_mounts = [
            *boot_volume_mounts,
            {"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR, "readOnly": True},
        ]
        volumes = [
            *boot_volumes,
            {"name": BACKUP_PVC_VOLUME_KEY, "persistentVolumeClaim": {"claimName": backup_pvc_name}},
        ]
        if include_restore_work_volume:
            volume_mounts.append({"name": RESTORE_WORK_VOLUME_KEY, "mountPath": RESTORE_WORK_MOUNT_PATH})
            volumes.append({"name": RESTORE_WORK_VOLUME_KEY, "emptyDir": {}})

        _run_python_runner_pod(
            pod_name=f"cbt-rstr-{restore_id}-{pod_name_suffix}",
            namespace=namespace,
            client=client,
            runner_script_filename=runner_script_filename,
            container_name=container_name,
            params_env_name=params_env_name,
            runner_params=runner_params,
            volume_mounts=volume_mounts,
            volume_devices=boot_volume_devices or None,
            volumes=volumes,
            wait_timeout=TIMEOUT_30MIN,
            pod_role=pod_role,
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
    """Restore boot disk from the QCOW2 chain on a push-mode backup PVC."""
    target_file = _restore_target_path(volume_mode=volume_mode)
    return _restore_vm_from_backup_pvc(
        restored_vm_name=restored_vm_name,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=size,
        volume_mode=volume_mode,
        access_mode=access_mode,
        backup_pvc_name=backup_pvc_name,
        boot_volume_name=boot_volume_name,
        os_flavor=os_flavor,
        vm_preference_name=vm_preference_name,
        vm_instance_type_name=vm_instance_type_name,
        runner_script_filename="push_restore_runner.py",
        container_name="cbt-push-restore",
        params_env_name=PUSH_RESTORE_PARAMS_ENV,
        runner_params=build_push_restore_params(volume_name=boot_volume_name, target_file=target_file),
        pod_name_suffix="push",
        pod_role="push restore",
        include_restore_work_volume=True,
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
    """Restore boot disk from the latest raw snapshot on pull-mode client storage."""
    target_file = _restore_target_path(volume_mode=volume_mode)
    return _restore_vm_from_backup_pvc(
        restored_vm_name=restored_vm_name,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=size,
        volume_mode=volume_mode,
        access_mode=access_mode,
        backup_pvc_name=client_backup_pvc_name,
        boot_volume_name=boot_volume_name,
        os_flavor=os_flavor,
        vm_preference_name=vm_preference_name,
        vm_instance_type_name=vm_instance_type_name,
        runner_script_filename="pull_restore_runner.py",
        container_name="cbt-pull-restore",
        params_env_name=PULL_RESTORE_PARAMS_ENV,
        runner_params=build_pull_restore_params(
            volume_name=boot_volume_name,
            target_file=target_file,
            volume_mode=volume_mode,
        ),
        pod_name_suffix="client",
        pod_role="pull client restore",
    )


def _restore_and_start_vm(
    *,
    vm: VirtualMachineForTests,
    namespace: str,
    client: DynamicClient,
    storage_class: str,
    size: str,
    volume_mode: str,
    access_mode: str,
    boot_volume_name: str,
    restore_vm_func: Callable[..., VirtualMachineForTests],
    restore_backup_kwargs: dict[str, str],
    ssh_timeout: int = TIMEOUT_5MIN,
) -> Generator[VirtualMachineForTests]:
    """Delete the source VM, restore from backup storage, start it, then clean up."""
    restored_vm_name = vm.name
    if restored_vm_name is None:
        raise RuntimeError("Cannot restore: source VM has no name")
    restore_spec = capture_restore_spec_and_delete_vm(vm=vm)
    restored_vm = restore_vm_func(
        restored_vm_name=restored_vm_name,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=size,
        volume_mode=volume_mode,
        access_mode=access_mode,
        boot_volume_name=boot_volume_name,
        **restore_backup_kwargs,
        **restore_spec,
    )
    running_vm(vm=restored_vm, ssh_timeout=ssh_timeout)
    try:
        yield restored_vm
    finally:
        restored_vm.delete(wait=True)


def restore_and_start_vm_from_push_backup(
    *,
    vm: VirtualMachineForTests,
    backup: VirtualMachineBackup,
    namespace: str,
    client: DynamicClient,
    storage_class: str,
    size: str,
    volume_mode: str,
    access_mode: str,
    backup_pvc_name: str,
    ssh_timeout: int = TIMEOUT_5MIN,
) -> Generator[VirtualMachineForTests]:
    """Delete the source VM, restore from a push backup, start it, then clean up."""
    yield from _restore_and_start_vm(
        vm=vm,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=size,
        volume_mode=volume_mode,
        access_mode=access_mode,
        boot_volume_name=included_boot_volume(backup=backup)["volumeName"],
        restore_vm_func=restore_vm_from_push_backup,
        restore_backup_kwargs={"backup_pvc_name": backup_pvc_name},
        ssh_timeout=ssh_timeout,
    )


def restore_and_start_vm_from_pull_client_backup(
    *,
    vm: VirtualMachineForTests,
    client_backup_pvc_name: str,
    namespace: str,
    client: DynamicClient,
    storage_class: str,
    size: str,
    volume_mode: str,
    access_mode: str,
    ssh_timeout: int = TIMEOUT_5MIN,
) -> Generator[VirtualMachineForTests]:
    """Delete the source VM, restore from pull client storage, start it, then clean up."""
    # Collect stores raw files under the backup status volumeName; capture it before
    # the original VM is deleted so restore can scope to that directory.
    boot_volume_name = vm.instance.spec.template.spec.volumes[0]["name"]
    yield from _restore_and_start_vm(
        vm=vm,
        namespace=namespace,
        client=client,
        storage_class=storage_class,
        size=size,
        volume_mode=volume_mode,
        access_mode=access_mode,
        boot_volume_name=boot_volume_name,
        restore_vm_func=restore_vm_from_pull_client_backup,
        restore_backup_kwargs={"client_backup_pvc_name": client_backup_pvc_name},
        ssh_timeout=ssh_timeout,
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
