"""CBT backup/restore utilities."""

import hashlib
import json
import logging
import re
import shlex
from collections.abc import Generator
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
from utilities.constants.networking import POD_CONTAINER_SPEC
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
CHECKPOINT_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


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
    """Return a short stable identifier for CBT resource names."""
    return hashlib.sha256(name.encode()).hexdigest()[:10]


def pull_collect_params_for_backup(
    *,
    backup: VirtualMachineBackup,
    export_token: str,
    boot_disk_size: str,
    force_full_backup: bool,
) -> dict[str, Any]:
    """Build pull collect runner parameters from a ready pull-mode backup."""
    # Single-disk VMs only on this path; take the sole included volume.
    included_volume = backup.instance.status["includedVolumes"][0]
    volume_name = included_volume["volumeName"]
    checkpoint_name = backup.instance.status["checkpointName"]
    checkpoint_timestamp = CHECKPOINT_TIMESTAMP_PATTERN.search(string=checkpoint_name)
    if not checkpoint_timestamp:
        raise RuntimeError(
            f"Checkpoint name {checkpoint_name!r} has no {CHECKPOINT_TIMESTAMP_PATTERN.pattern} timestamp"
        )
    return {
        "endpoint_cert": backup.instance.status["endpointCert"],
        "export_token": export_token,
        "map_endpoint": included_volume["mapEndpoint"],
        "data_endpoint": included_volume["dataEndpoint"],
        "disk_size_bytes": int(parse_quantity(boot_disk_size)),
        "raw_file": f"{BACKUP_DIR}/{volume_name}/{checkpoint_timestamp.group(1)}/{volume_name}.raw",
        "force_full_backup": force_full_backup,
    }


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
    """Create an online pull-mode backup, collect extents to client PVC storage, then delete the backup CR.

    Collection to the client PVC is test-side stand-in storage for validating pull export;
    it is not product offline-backup support.
    """
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
        # Pull readiness is ExportReady=True (Progressing stays True until the export is consumed).
        backup.wait_for_condition(
            condition="ExportReady",
            status=VirtualMachineBackup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            sleep_time=TIMEOUT_5SEC,
        )
        _run_python_runner_pod(
            pod_name=f"cbt-pull-collect-{cbt_resource_id(name=f'{backup.name}-collect')}",
            namespace=namespace,
            client=client,
            runner_script_filename="pull_collect_runner.py",
            runner_params=pull_collect_params_for_backup(
                backup=backup,
                export_token=export_token,
                boot_disk_size=boot_disk_size,
                force_full_backup=force_full_backup,
            ),
            volume_mounts=[{"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR}],
            volumes=[
                {
                    "name": BACKUP_PVC_VOLUME_KEY,
                    "persistentVolumeClaim": {"claimName": client_backup_pvc_name},
                }
            ],
        )
        LOGGER.info(f"Pull backup collection complete for {backup.name}; deleting backup CR")
        backup.delete(wait=True)
        backup.teardown = False


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
    restored_vm_name = vm.name
    boot_volume_name = vm.instance.spec.template.spec.volumes[0]["name"]
    vm_instance_type_name = vm.instance.spec["instancetype"]["name"]
    vm_preference_name = vm.instance.spec["preference"]["name"]
    os_flavor = vm.os_flavor
    vm.delete(wait=True)
    vm.teardown = False

    restore_id = cbt_resource_id(name=restored_vm_name)
    boot_is_block = volume_mode == DataVolume.VolumeMode.BLOCK
    # Block PVCs use volumeDevices; Filesystem PVCs use volumeMounts + disk.img.
    target_file = BOOT_VOLUME_DEVICE_PATH if boot_is_block else f"{BOOT_VOLUME_MOUNT_PATH}/disk.img"
    LOGGER.info(f"CBT pull restore {restored_vm_name}: boot_volume_name={boot_volume_name}")
    # teardown=False so the with-block exit does not delete the boot PVC while the VM still
    # references it; cleanup deletes the VM first, then the PVC.
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
        restored_vm = None
        try:
            boot_volume = {
                "name": BOOT_VOLUME_MOUNT_KEY,
                "persistentVolumeClaim": {"claimName": boot_pvc.name},
            }
            if boot_is_block:
                boot_volume_mounts: list[dict[str, Any]] = []
                boot_volume_devices: list[dict[str, Any]] | None = [
                    {"name": BOOT_VOLUME_MOUNT_KEY, "devicePath": BOOT_VOLUME_DEVICE_PATH}
                ]
            else:
                boot_volume_mounts = [{"name": BOOT_VOLUME_MOUNT_KEY, "mountPath": BOOT_VOLUME_MOUNT_PATH}]
                boot_volume_devices = None
            _run_python_runner_pod(
                pod_name=f"cbt-rstr-{restore_id}-client",
                namespace=namespace,
                client=client,
                runner_script_filename="pull_restore_runner.py",
                runner_params={
                    "volume_name": boot_volume_name,
                    "target_file": target_file,
                    "volume_mode": volume_mode,
                },
                volume_mounts=[
                    *boot_volume_mounts,
                    {"name": BACKUP_PVC_VOLUME_KEY, "mountPath": BACKUP_DIR, "readOnly": True},
                ],
                volume_devices=boot_volume_devices,
                volumes=[
                    boot_volume,
                    {
                        "name": BACKUP_PVC_VOLUME_KEY,
                        "persistentVolumeClaim": {"claimName": client_backup_pvc_name},
                    },
                ],
            )
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
            running_vm(vm=restored_vm, ssh_timeout=ssh_timeout)
            yield restored_vm
        finally:
            try:
                if restored_vm is not None:
                    restored_vm.delete(wait=True)
            finally:
                boot_pvc.delete(wait=True)


_RUNNER_PARAMS_ENV_BY_SCRIPT = {
    "pull_collect_runner.py": PULL_COLLECT_PARAMS_ENV,
    "pull_restore_runner.py": PULL_RESTORE_PARAMS_ENV,
}


def _run_python_runner_pod(
    *,
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    runner_script_filename: str,
    runner_params: dict[str, Any],
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    volume_devices: list[dict[str, Any]] | None = None,
    wait_timeout: int = TIMEOUT_30MIN,
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
                    "name": _RUNNER_PARAMS_ENV_BY_SCRIPT[runner_script_filename],
                    "value": json.dumps(runner_params),
                }
            ],
            wait_timeout=wait_timeout,
        )


def _pod_debug_context(client_pod: Pod) -> str:
    """Return pod phase and logs for failure diagnostics."""
    client_pod.get()
    try:
        pod_logs = client_pod.log(container=POD_CONTAINER_SPEC["name"])
    except ApiException as log_error:
        pod_logs = f"<unavailable: {log_error}>"
    return f"phase={client_pod.instance.status.phase}\nlogs:\n{pod_logs}"


def _run_one_shot_client_pod(
    *,
    pod_name: str,
    namespace: str,
    client: DynamicClient,
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    container_command: list[str],
    volume_devices: list[dict[str, Any]] | None = None,
    container_env: list[dict[str, str]] | None = None,
    wait_timeout: int = TIMEOUT_30MIN,
) -> None:
    """Run a single-purpose client pod whose main process runs to completion."""
    container_spec: dict[str, Any] = {
        **POD_CONTAINER_SPEC,
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
        LOGGER.info(f"Running CBT pod {pod_name} in {namespace}")
        try:
            client_pod.wait_for_status(
                status=Pod.Status.SUCCEEDED,
                timeout=wait_timeout,
                stop_status=Pod.Status.FAILED,
                sleep=TIMEOUT_5SEC,
            )
        except TimeoutExpiredError as wait_error:
            raise RuntimeError(
                f"CBT pod {client_pod.name} did not succeed: {wait_error}. {_pod_debug_context(client_pod=client_pod)}"
            ) from wait_error
        LOGGER.info(f"CBT pod {client_pod.name} completed successfully")
