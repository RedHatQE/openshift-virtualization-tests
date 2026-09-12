from __future__ import annotations

import base64
import logging
import shlex
import tarfile
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.config_map import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.resource import NamespacedResource
from ocp_resources.storage_class import StorageClass
from ocp_resources.volume_snapshot import VolumeSnapshot
from ocp_resources.volume_snapshot_class import VolumeSnapshotClass
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.file_level_restore.constants import (
    CONFIGMAP_LINUX_HELPERS_TAR,
    CONFIGMAP_SSH_PUBLIC_KEY,
    CONFIGMAP_WINDOWS_HELPERS_TAR,
    FILE_RESTORE_OPERATOR_DEPLOYMENT_NAME,
    FILE_RESTORE_OPERATOR_NAMESPACE,
    FILE_RESTORE_SSH_CONFIGMAP_NAME,
    LINUX_DATA_DISK_MOUNT_PATH,
    LINUX_FILERESTORE_SCRIPT,
    LINUX_RESTORE_TEST_DIRECTORY,
    LINUX_SETUP_SCRIPT,
    LINUX_TEST_FILE_NAME,
    OPERATOR_SSH_PUBLIC_KEY_FILE_NAME,
    RESTORE_VOLUME_SUFFIX,
    WINDOWS_DATA_DISK_LETTER,
    WINDOWS_FILERESTORE_SCRIPT,
    WINDOWS_HELPER_STAGE_DIRECTORY,
    WINDOWS_SETUP_SCRIPT,
)
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_5SEC
from utilities.storage import wait_for_volume_snapshot_ready_to_use

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


class VirtualMachineFileRestore(NamespacedResource):
    """KubeVirt VirtualMachineFileRestore custom resource."""

    api_group: str = "filerestore.kubevirt.io"

    class Phase:
        NEW = "New"
        INIT = "Init"
        HOTPLUGGING = "Hotplugging"
        WAITING_FOR_ATTACHMENT = "WaitingForAttachment"
        SSH_CONNECTING = "SSHConnecting"
        RESTORING = "Restoring"
        VOLUME_READY = "VolumeReady"
        CLEANUP = "Cleanup"
        SUCCEEDED = "Succeeded"
        FAILED = "Failed"

    def __init__(
        self,
        target_vm_name: str,
        source_snapshot_name: str | None = None,
        source_pvc_name: str | None = None,
        source_path: str | None = None,
        source_partition: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a VirtualMachineFileRestore resource.

        Args:
            target_vm_name: Name of the target VirtualMachine.
            source_snapshot_name: VolumeSnapshot name to restore from.
            source_pvc_name: PVC name to restore from.
            source_path: Path on the source volume to restore. Restored to the same
                path on the guest root filesystem (operator does not support targetPath).
            source_partition: Partition number on the source volume.
            **kwargs: Additional arguments passed to NamespacedResource.
        """
        super().__init__(**kwargs)
        self._target_vm_name = target_vm_name
        self._source_snapshot_name = source_snapshot_name
        self._source_pvc_name = source_pvc_name
        self._source_path = source_path
        self._source_partition = source_partition

    def to_dict(self) -> None:
        """Build the VirtualMachineFileRestore manifest in ``self.res``.

        Calls the base ``to_dict()`` first, then populates ``spec`` when this
        resource was constructed programmatically (no ``kind_dict`` or
        ``yaml_file``). The guard prevents duplicate spec injection if
        ``to_dict()`` is invoked more than once.

        Side effects:
            Mutates ``self.res`` in place by updating ``spec``.
        """
        super().to_dict()
        if not self.kind_dict and not self.yaml_file:
            spec: dict[str, Any] = {
                "target": {
                    "apiGroup": "kubevirt.io",
                    "kind": "VirtualMachine",
                    "name": self._target_vm_name,
                },
                "source": {},
            }

            if self._source_snapshot_name:
                spec["source"]["snapshot"] = {"name": self._source_snapshot_name}
            elif self._source_pvc_name:
                spec["source"]["pvc"] = {"name": self._source_pvc_name}
            else:
                raise ValueError("VirtualMachineFileRestore requires either source_snapshot_name or source_pvc_name")

            if self._source_path is not None:
                spec["sourcePath"] = self._source_path
            if self._source_partition is not None:
                spec["sourcePartition"] = self._source_partition

            self.res.setdefault("spec", {}).update(spec)


def volume_snapshot_class_for_storage_class(storage_class_name: str, admin_client: DynamicClient) -> str:
    """Find the VolumeSnapshotClass matching a StorageClass provisioner.

    Args:
        storage_class_name: Name of the StorageClass.
        admin_client: Kubernetes admin client.

    Returns:
        Name of the matching VolumeSnapshotClass.

    Raises:
        ValueError: If no matching VolumeSnapshotClass is found.
    """
    provisioner = StorageClass(client=admin_client, name=storage_class_name).instance.get("provisioner")
    for volume_snapshot_class in VolumeSnapshotClass.get(client=admin_client):
        if volume_snapshot_class.instance.get("driver") == provisioner:
            return volume_snapshot_class.name
    raise ValueError(
        f"No VolumeSnapshotClass found for StorageClass '{storage_class_name}' (provisioner: {provisioner})"
    )


@contextmanager
def windows_data_disk_volume_snapshot(
    vm: VirtualMachineForTests,
    pvc_name: str,
    snapshot_name: str,
    namespace_name: str,
    storage_class_name: str,
    admin_client: DynamicClient,
) -> Iterator[VolumeSnapshot]:
    """Create a ready VolumeSnapshot of a Windows VM data disk PVC.

    Flushes the guest filesystem cache, resolves the VolumeSnapshotClass, creates the
    snapshot, and waits until it is ready to use.

    Args:
        vm: Running Windows VM whose data disk will be snapshotted.
        pvc_name: Name of the data disk PVC to snapshot.
        snapshot_name: Name for the VolumeSnapshot resource.
        namespace_name: Namespace for the VolumeSnapshot.
        storage_class_name: StorageClass used to resolve the VolumeSnapshotClass.
        admin_client: Kubernetes admin client.

    Yields:
        Ready VolumeSnapshot of the Windows data disk PVC.
    """
    LOGGER.info("Flushing Windows filesystem cache before snapshot")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "powershell",
            "-NoProfile",
            "-Command",
            f"Write-VolumeCache -DriveLetter {WINDOWS_DATA_DISK_LETTER}",
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    volume_snapshot_class_name = volume_snapshot_class_for_storage_class(
        storage_class_name=storage_class_name,
        admin_client=admin_client,
    )
    LOGGER.info(f"Creating VolumeSnapshot '{snapshot_name}' of Windows data disk PVC '{pvc_name}'")
    with VolumeSnapshot(
        name=snapshot_name,
        namespace=namespace_name,
        source={"persistentVolumeClaimName": pvc_name},
        volume_snapshot_class_name=volume_snapshot_class_name,
        client=admin_client,
    ) as snapshot:
        wait_for_volume_snapshot_ready_to_use(namespace=namespace_name, name=snapshot.name, client=admin_client)
        yield snapshot


def wait_for_file_restore_operator_ready(admin_client: DynamicClient) -> None:
    """Wait for the HCO-managed file-restore operator deployment and ConfigMap to be ready.

    Args:
        admin_client: Kubernetes admin client.

    Raises:
        RuntimeError: If the operator deployment or ConfigMap is not ready in time.
    """
    LOGGER.info(
        f"Waiting for file-restore operator deployment '{FILE_RESTORE_OPERATOR_DEPLOYMENT_NAME}'"
        f" in namespace '{FILE_RESTORE_OPERATOR_NAMESPACE}'"
    )
    deployment = Deployment(
        name=FILE_RESTORE_OPERATOR_DEPLOYMENT_NAME,
        namespace=FILE_RESTORE_OPERATOR_NAMESPACE,
        client=admin_client,
    )
    deployment.wait_for_replicas(timeout=TIMEOUT_5MIN)
    get_file_restore_operator_configmap(admin_client=admin_client)
    LOGGER.info("File-restore operator is ready")


def get_file_restore_operator_configmap(admin_client: DynamicClient) -> ConfigMap:
    """Fetch the file-restore operator SSH and guest-helper ConfigMap.

    Args:
        admin_client: Kubernetes admin client.

    Returns:
        The operator ConfigMap resource.

    Raises:
        RuntimeError: If the ConfigMap is missing required keys.
    """
    LOGGER.info(f"Waiting for ConfigMap '{FILE_RESTORE_SSH_CONFIGMAP_NAME}'")
    config_map = ConfigMap(
        name=FILE_RESTORE_SSH_CONFIGMAP_NAME,
        namespace=FILE_RESTORE_OPERATOR_NAMESPACE,
        client=admin_client,
    )
    config_map_not_ready_error = (
        f"ConfigMap '{FILE_RESTORE_SSH_CONFIGMAP_NAME}' in '{FILE_RESTORE_OPERATOR_NAMESPACE}'"
        " is missing ssh-publickey or guest helper tarballs"
    )
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: config_map.instance,
        ):
            if not sample:
                continue
            config_map_dict = _config_map_as_dict(config_map_instance=sample)
            ssh_public_key = (config_map_dict.get("data") or {}).get(CONFIGMAP_SSH_PUBLIC_KEY, "")
            try:
                linux_helpers = _get_configmap_binary_value(
                    config_map_instance=sample,
                    key=CONFIGMAP_LINUX_HELPERS_TAR,
                )
                windows_helpers = _get_configmap_binary_value(
                    config_map_instance=sample,
                    key=CONFIGMAP_WINDOWS_HELPERS_TAR,
                )
            except RuntimeError as err:
                LOGGER.info(f"ConfigMap '{FILE_RESTORE_SSH_CONFIGMAP_NAME}' binary keys not yet ready: {err}")
                continue
            if ssh_public_key and linux_helpers and windows_helpers:
                LOGGER.info("File-restore operator ConfigMap is ready with guest helper tarballs")
                return config_map
    except TimeoutExpiredError as err:
        raise RuntimeError(config_map_not_ready_error) from err
    raise RuntimeError(config_map_not_ready_error)


def _ssh_public_key_from_config_map(config_map: ConfigMap) -> str:
    """Extract the operator SSH public key from a ConfigMap resource.

    Args:
        config_map: File-restore operator ConfigMap.

    Returns:
        The operator SSH public key string.

    Raises:
        RuntimeError: If the SSH public key entry is missing or empty.
    """
    ssh_public_key = _get_configmap_data_value(
        config_map_instance=config_map.instance,
        key=CONFIGMAP_SSH_PUBLIC_KEY,
    ).strip()
    if not ssh_public_key:
        raise RuntimeError("File-restore operator SSH public key is empty")
    return ssh_public_key


def extract_helper_tar(tar_bytes: bytes) -> dict[str, str]:
    """Extract an uncompressed helper tar archive into a filename-to-content map.

    Args:
        tar_bytes: Raw tar archive bytes.

    Returns:
        Mapping of archive member names to file contents.
    """
    files: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as temp_directory:
        tar_path = Path(temp_directory) / "helpers.tar"
        tar_path.write_bytes(data=tar_bytes)
        with tarfile.open(name=tar_path, mode="r:") as tar_archive:
            tar_archive.extractall(path=temp_directory, filter="data")
        for extracted_path in Path(temp_directory).iterdir():
            if extracted_path.is_file() and extracted_path.name != tar_path.name:
                files[extracted_path.name] = extracted_path.read_text(encoding="utf-8")
    return files


def install_linux_guest_helper(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Install the Linux guest helper from the operator ConfigMap on a running VM.

    Args:
        vm: Running Linux VM to configure.
        admin_client: Kubernetes admin client.
    """
    config_map = get_file_restore_operator_configmap(admin_client=admin_client)
    operator_public_key = _ssh_public_key_from_config_map(config_map=config_map)
    linux_tar = _get_configmap_binary_value(
        config_map_instance=config_map.instance,
        key=CONFIGMAP_LINUX_HELPERS_TAR,
    )
    scripts = extract_helper_tar(tar_bytes=linux_tar)
    if LINUX_SETUP_SCRIPT not in scripts or LINUX_FILERESTORE_SCRIPT not in scripts:
        raise RuntimeError(f"Linux helper tar is missing {LINUX_SETUP_SCRIPT} or {LINUX_FILERESTORE_SCRIPT}")

    stage_directory = f"/tmp/filerestore-helper-{time.time_ns()}"
    LOGGER.info(f"Staging Linux guest helpers on VM '{vm.name}' in {stage_directory}")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=["mkdir", "-m", "0700", "-p", stage_directory],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    for script_name in (LINUX_SETUP_SCRIPT, LINUX_FILERESTORE_SCRIPT):
        script_path = f"{stage_directory}/{script_name}"
        encoded_script = base64.b64encode(scripts[script_name].encode()).decode()
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[
                "sudo",
                "bash",
                "-c",
                (
                    f"echo {encoded_script} | base64 -d > {script_path} "
                    f"&& chown root:root {script_path} && chmod 0644 {script_path}"
                ),
            ],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )

    key_file_path = f"{stage_directory}/{OPERATOR_SSH_PUBLIC_KEY_FILE_NAME}"
    encoded_public_key = base64.b64encode(operator_public_key.encode()).decode()
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "bash",
            "-c",
            f"echo {encoded_public_key} | base64 -d > {key_file_path} && chmod 0600 {key_file_path}",
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    setup_script_path = f"{stage_directory}/{LINUX_SETUP_SCRIPT}"
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "bash",
            "-c",
            f'sudo bash {setup_script_path} "$(cat {key_file_path})"',
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=["sudo", "rm", "-rf", stage_directory],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    LOGGER.info(f"Linux guest helper installed on VM '{vm.name}'")


def stage_windows_helper_scripts(
    vm: VirtualMachineForTests,
    remote_directory: str,
    scripts: dict[str, str],
) -> None:
    """Stage helper scripts from the operator ConfigMap onto a Windows VM.

    Scripts are extracted from the ConfigMap tarball locally, then transferred with
    SFTP to avoid Windows SSH command-line length limits on large setup.bat payloads.

    Args:
        vm: Running Windows VM with SSH connectivity.
        remote_directory: Directory that will contain the staged helper scripts.
        scripts: Mapping of script file name to script body from the ConfigMap tarball.
    """
    LOGGER.info(f"Staging Windows helper scripts on VM '{vm.name}' in {remote_directory}")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "powershell",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Directory -Path '{remote_directory}' -Force | Out-Null",
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    with tempfile.TemporaryDirectory() as temp_directory:
        for script_name, script_content in scripts.items():
            local_path = Path(temp_directory) / script_name
            local_path.write_bytes(data=script_content.encode())
            remote_sftp_path = f"{remote_directory}/{script_name}".replace("\\", "/")
            vm.ssh_exec.fs.put(path_src=str(local_path), path_dst=remote_sftp_path)


def install_windows_guest_helper(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Install the Windows guest helper from the operator ConfigMap on a running VM.

    Args:
        vm: Running Windows VM to configure.
        admin_client: Kubernetes admin client.
    """
    config_map = get_file_restore_operator_configmap(admin_client=admin_client)
    operator_public_key = _ssh_public_key_from_config_map(config_map=config_map)
    windows_tar = _get_configmap_binary_value(
        config_map_instance=config_map.instance,
        key=CONFIGMAP_WINDOWS_HELPERS_TAR,
    )
    scripts = extract_helper_tar(tar_bytes=windows_tar)
    if WINDOWS_SETUP_SCRIPT not in scripts or WINDOWS_FILERESTORE_SCRIPT not in scripts:
        raise RuntimeError(f"Windows helper tar is missing {WINDOWS_SETUP_SCRIPT} or {WINDOWS_FILERESTORE_SCRIPT}")

    LOGGER.info(f"Installing Windows guest helpers on VM '{vm.name}' from ConfigMap tarball")
    stage_windows_helper_scripts(
        vm=vm,
        remote_directory=WINDOWS_HELPER_STAGE_DIRECTORY,
        scripts={
            WINDOWS_SETUP_SCRIPT: scripts[WINDOWS_SETUP_SCRIPT],
            WINDOWS_FILERESTORE_SCRIPT: scripts[WINDOWS_FILERESTORE_SCRIPT],
        },
    )

    windows_key_path = windows_guest_path(
        guest_path=f"{WINDOWS_HELPER_STAGE_DIRECTORY}/{OPERATOR_SSH_PUBLIC_KEY_FILE_NAME}",
    )
    remote_key_sftp_path = windows_key_path.replace("\\", "/")
    with tempfile.TemporaryDirectory() as temp_directory:
        local_key_path = Path(temp_directory) / OPERATOR_SSH_PUBLIC_KEY_FILE_NAME
        local_key_path.write_text(data=operator_public_key, encoding="utf-8")
        vm.ssh_exec.fs.put(path_src=str(local_key_path), path_dst=remote_key_sftp_path)

    setup_script_path = windows_guest_path(
        guest_path=f"{WINDOWS_HELPER_STAGE_DIRECTORY}/{WINDOWS_SETUP_SCRIPT}",
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "powershell",
            "-NoProfile",
            "-Command",
            (f"$pubKey = (Get-Content -LiteralPath '{windows_key_path}' -Raw).Trim(); & '{setup_script_path}' $pubKey"),
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "powershell",
            "-NoProfile",
            "-Command",
            f"Remove-Item -LiteralPath '{WINDOWS_HELPER_STAGE_DIRECTORY}' -Recurse -Force",
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    LOGGER.info(f"Windows guest helper installed on VM '{vm.name}'")


def wait_for_file_restore_phase(
    file_restore: VirtualMachineFileRestore,
    target_phase: str,
    timeout: int = TIMEOUT_5MIN,
) -> None:
    """Wait for VirtualMachineFileRestore to reach a target phase.

    Args:
        file_restore: The VirtualMachineFileRestore resource to monitor.
        target_phase: The phase to wait for.
        timeout: Maximum wait time in seconds.

    Raises:
        AssertionError: If the restore reaches Failed phase.
    """
    LOGGER.info(f"Waiting for VirtualMachineFileRestore '{file_restore.name}' to reach phase '{target_phase}'")
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: file_restore.instance.get("status", {}),
    ):
        phase = sample.get("phase")
        LOGGER.info(f"VirtualMachineFileRestore '{file_restore.name}' phase: {phase}")
        if phase == target_phase:
            return
        if phase == VirtualMachineFileRestore.Phase.FAILED:
            error_message = sample.get("errorMessage", "Unknown error")
            raise AssertionError(f"VirtualMachineFileRestore '{file_restore.name}' failed: {error_message}")


def get_restored_files_count(file_restore: VirtualMachineFileRestore) -> int:
    """Return restoredFilesCount from the VirtualMachineFileRestore status.

    Args:
        file_restore: The VirtualMachineFileRestore resource.

    Returns:
        Number of files reported as restored.

    Raises:
        AssertionError: If restoredFilesCount is not set.
    """
    restored_files_count = file_restore.instance.get("status", {}).get("restoredFilesCount")
    assert restored_files_count is not None, (
        f"VirtualMachineFileRestore '{file_restore.name}' status.restoredFilesCount is not set"
    )
    return int(restored_files_count)


def restore_volume_name(restore_cr_name: str) -> str:
    """Return the hotplug volume name used by the operator for a restore CR.

    Args:
        restore_cr_name: VirtualMachineFileRestore resource name.

    Returns:
        Hotplug volume name attached during restore.
    """
    return f"{restore_cr_name}{RESTORE_VOLUME_SUFFIX}"


def assert_restore_volume_detached(vm: VirtualMachineForTests, restore_cr_name: str) -> None:
    """Assert the restore hotplug volume is no longer attached to the VMI.

    Args:
        vm: Target virtual machine.
        restore_cr_name: VirtualMachineFileRestore resource name.

    Raises:
        AssertionError: If the restore volume is still present on the VMI.
    """
    volume_name = restore_volume_name(restore_cr_name=restore_cr_name)
    vmi = vm.vmi.instance
    spec_volume_names = {volume.name for volume in vmi.spec.volumes}
    status_volume_names = {volume_status.get("name") for volume_status in vmi.status.volumeStatus or []}
    assert volume_name not in spec_volume_names, f"Restore volume '{volume_name}' is still present in VMI spec volumes"
    assert volume_name not in status_volume_names, (
        f"Restore volume '{volume_name}' is still present in VMI status volumeStatus"
    )


def assert_no_managed_restore_data_volume(
    namespace_name: str,
    restore_cr_name: str,
    admin_client: DynamicClient,
) -> None:
    """Assert no operator-managed restore DataVolume remains for the restore CR.

    Args:
        namespace_name: Namespace containing the restore CR.
        restore_cr_name: VirtualMachineFileRestore resource name.
        admin_client: Kubernetes admin client.

    Raises:
        AssertionError: If the managed restore DataVolume still exists.
    """
    data_volume_name = restore_volume_name(restore_cr_name=restore_cr_name)
    data_volume = DataVolume(
        name=data_volume_name,
        namespace=namespace_name,
        client=admin_client,
        api_name="pvc",
    )
    try:
        data_volume.instance
    except NotFoundError:
        return
    raise AssertionError(
        f"Expected restore DataVolume '{data_volume_name}' to be deleted from namespace '{namespace_name}'"
    )


def assert_successful_restore_cleanup(
    vm: VirtualMachineForTests,
    restore_cr_name: str,
    namespace_name: str,
    admin_client: DynamicClient,
    snapshot_source: bool,
) -> None:
    """Assert temporary restore resources are cleaned up after a successful restore.

    Args:
        vm: Target virtual machine.
        restore_cr_name: VirtualMachineFileRestore resource name.
        namespace_name: Namespace containing restore resources.
        admin_client: Kubernetes admin client.
        snapshot_source: Whether the restore source was a VolumeSnapshot.
    """
    assert_restore_volume_detached(vm=vm, restore_cr_name=restore_cr_name)
    if snapshot_source:
        assert_no_managed_restore_data_volume(
            namespace_name=namespace_name,
            restore_cr_name=restore_cr_name,
            admin_client=admin_client,
        )


def linux_restore_test_file_path(username: str) -> str:
    """Return the Linux restore path for the standard test file.

    The path is relative to the backup volume root and to the guest root after restore.

    Args:
        username: SSH username of the Linux VM.

    Returns:
        Guest-root path used for sourcePath and post-restore verification.
    """
    return f"/home/{username}/{LINUX_RESTORE_TEST_DIRECTORY}/{LINUX_TEST_FILE_NAME}"


def windows_guest_path(guest_path: str) -> str:
    """Normalize a Windows guest path for PowerShell and sourcePath.

    Args:
        guest_path: Windows path using forward or backslashes.

    Returns:
        Windows path with backslashes.
    """
    return guest_path.replace("/", "\\")


def delete_windows_guest_file(vm: VirtualMachineForTests, guest_path: str) -> None:
    """Delete a file from a Windows VM guest filesystem.

    Args:
        vm: Running Windows VM with SSH connectivity.
        guest_path: Windows guest path to the file using forward or backslashes.
    """
    powershell_path = windows_guest_path(guest_path=guest_path)
    LOGGER.info(f"Deleting Windows test file '{powershell_path}'")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            "powershell",
            "-NoProfile",
            "-Command",
            f"Remove-Item -LiteralPath '{powershell_path}' -Force -ErrorAction Stop",
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )


def windows_data_disk_path(relative_path: str) -> str:
    """Build a full Windows path on the NTFS data disk.

    Args:
        relative_path: Path after the drive letter.

    Returns:
        Guest path using forward slashes (for constants and verify helpers).
    """
    normalized_path = relative_path.replace("\\", "/").lstrip("/")
    return f"{WINDOWS_DATA_DISK_LETTER}:/{normalized_path}"


def linux_data_disk_file_path(relative_path: str) -> str:
    """Map a restore-relative Linux path to its location on the mounted data disk.

    Args:
        relative_path: Path relative to the backup volume root and guest root.

    Returns:
        Absolute path on the mounted data disk.
    """
    return f"{LINUX_DATA_DISK_MOUNT_PATH}{relative_path}"


def ensure_linux_data_disk_directory(vm: VirtualMachineForTests, relative_directory: str) -> None:
    """Create a directory on the Linux VM data disk before writing test files.

    The data disk mount is world-writable; create directories as the SSH user so
    subsequent writes do not hit root-owned path permission errors.

    Args:
        vm: Running Linux VM with the data disk mounted.
        relative_directory: Directory path relative to the backup volume root.
    """
    directory_path = linux_data_disk_file_path(relative_path=relative_directory)
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=["mkdir", "-p", directory_path],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )


def virtio_disk_device_path(vm: VirtualMachineForTests, disk_name: str) -> str:
    """Return the guest /dev/vdX path for a virtio disk attached to the VM.

    Args:
        vm: Running virtual machine with the target disk attached.
        disk_name: Volume name of the virtio disk in the VMI spec.

    Returns:
        Block device path such as /dev/vdc.

    Raises:
        ValueError: If the named virtio disk is not present on the VM.
    """
    virtio_disk_names: list[str] = []
    for disk_entry in vm.vmi.instance.spec.domain.devices.disks:
        disk_spec = disk_entry.get("disk")
        if not disk_spec or disk_spec.get("bus") != "virtio":
            continue
        entry_name = disk_entry.get("name")
        if entry_name:
            virtio_disk_names.append(entry_name)
    if disk_name not in virtio_disk_names:
        raise ValueError(
            f"Virtio disk '{disk_name}' not found on VM '{vm.name}'. Available virtio disks: {virtio_disk_names}"
        )
    disk_index = virtio_disk_names.index(disk_name)
    return f"/dev/vd{chr(ord('a') + disk_index)}"


def format_and_mount_linux_data_disk(vm: VirtualMachineForTests, mount_path: str, data_disk_name: str) -> None:
    """Format and mount the Linux VM secondary data disk at the given path.

    Args:
        vm: Running Linux VM with a secondary data disk attached.
        mount_path: Mount point for the formatted ext4 filesystem.
        data_disk_name: DataVolume name of the secondary disk attached to the VM.
    """
    device_path = virtio_disk_device_path(vm=vm, disk_name=data_disk_name)
    LOGGER.info(f"Formatting and mounting Linux data disk '{device_path}' at '{mount_path}'")
    for command in (
        f"sudo mkfs.ext4 -F {device_path}",
        f"sudo mkdir -p {mount_path}",
        f"sudo mount {device_path} {mount_path}",
        f"sudo chmod 777 {mount_path}",
    ):
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(command),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )


def initialize_and_format_windows_data_disk(vm: VirtualMachineForTests, drive_letter: str) -> int:
    """Initialize, partition, and format the Windows VM secondary data disk as NTFS.

    Args:
        vm: Running Windows VM with a hotplugged secondary disk.
        drive_letter: Drive letter to assign to the formatted volume.

    Returns:
        Disk number of the initialized data disk.
    """
    disk_number_command = (
        "Get-Disk | Where-Object { $_.PartitionStyle -eq 'RAW' } |"
        " Sort-Object Number | Select-Object -First 1 -ExpandProperty Number"
    )
    disk_number_output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", disk_number_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )[0].strip()
    disk_number = int(disk_number_output)
    LOGGER.info(f"Initializing Windows data disk {disk_number} as drive {drive_letter}:")
    # GPT disks always get an MSR as partition 1; New-Partition creates the data volume as partition 2.
    # Avoid New-Partition -PassThru and -DriveLetter — not supported on all Windows/PowerShell builds.
    format_command = (
        f"Initialize-Disk -Number {disk_number} -PartitionStyle GPT;"
        f" New-Partition -DiskNumber {disk_number} -UseMaximumSize;"
        f" Set-Partition -DiskNumber {disk_number} -PartitionNumber 2 -NewDriveLetter {drive_letter};"
        f" Format-Volume -DriveLetter {drive_letter} -FileSystem NTFS -Confirm:$false"
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", format_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    return disk_number


def get_windows_file_acl_baseline(vm: VirtualMachineForTests, file_path: str) -> tuple[str, str]:
    """Capture NTFS ACL and owner SID for a file on a Windows VM.

    Args:
        vm: Windows VM with SSH connectivity.
        file_path: Full Windows path to the file.

    Returns:
        Tuple of SDDL ACL string and owner SID string.
    """
    acl_command = (
        f"$path = '{file_path}';"
        f" $acl = Get-Acl -LiteralPath $path;"
        f" $sddl = $acl.Sddl;"
        f" if (-not $sddl) {{ $sddl = $acl.GetSecurityDescriptorSddlForm('All') }};"
        f" Write-Output $sddl;"
        f" Write-Output '---';"
        f" Write-Output $acl.Owner"
    )
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", acl_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )[0]
    acl_string, owner_sid = output.split("---", maxsplit=1)
    acl_string = acl_string.strip()
    owner_sid = owner_sid.strip()
    if not acl_string or not owner_sid:
        raise RuntimeError(
            f"Failed to read NTFS ACL baseline for '{file_path}': acl='{acl_string}', owner='{owner_sid}'"
        )
    return acl_string, owner_sid


def assert_windows_ntfs_acl_matches(
    vm: VirtualMachineForTests,
    file_path: str,
    expected_acl: str,
    expected_owner: str,
) -> None:
    """Assert NTFS ACL and owner on a Windows file match the recorded baseline.

    Args:
        vm: Windows VM with SSH connectivity.
        file_path: Full Windows path to the file.
        expected_acl: Expected SDDL ACL string.
        expected_owner: Expected owner SID string.

    Raises:
        AssertionError: If ACL or owner does not match the baseline.
    """
    actual_acl, actual_owner = get_windows_file_acl_baseline(vm=vm, file_path=file_path)
    assert actual_acl == expected_acl, (
        f"NTFS ACL on '{file_path}' does not match baseline.\nExpected: {expected_acl}\nActual: {actual_acl}"
    )
    assert actual_owner == expected_owner, (
        f"Owner SID on '{file_path}' does not match baseline.\nExpected: {expected_owner}\nActual: {actual_owner}"
    )


def count_files_in_windows_directory(vm: VirtualMachineForTests, directory_path: str) -> int:
    """Count files in a Windows directory.

    Args:
        vm: Windows VM with SSH connectivity.
        directory_path: Directory path on the Windows guest.

    Returns:
        Number of files in the directory.
    """
    count_command = f"(Get-ChildItem -LiteralPath '{directory_path}' -File | Measure-Object).Count"
    count_output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", count_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )[0].strip()
    return int(count_output)


def _config_map_as_dict(config_map_instance: Any) -> dict[str, Any]:
    """Convert a ConfigMap ResourceInstance to a plain dictionary.

    Args:
        config_map_instance: Kubernetes ConfigMap instance object.

    Returns:
        ConfigMap fields as a dictionary.
    """
    if isinstance(config_map_instance, dict):
        return config_map_instance
    return config_map_instance.to_dict()


def _get_configmap_data_value(config_map_instance: Any, key: str) -> str:
    """Read a string ConfigMap entry from the data field.

    Args:
        config_map_instance: Kubernetes ConfigMap instance object.
        key: ConfigMap data key.

    Returns:
        String value for the requested ConfigMap entry.

    Raises:
        RuntimeError: If the key is not present in data.
    """
    config_map_dict = _config_map_as_dict(config_map_instance=config_map_instance)
    data = config_map_dict.get("data") or {}
    if key not in data:
        raise RuntimeError(f"ConfigMap key '{key}' not found in data")
    return data[key]


def _get_configmap_binary_value(config_map_instance: Any, key: str) -> bytes:
    """Read a binary ConfigMap entry, decoding base64 when required.

    Args:
        config_map_instance: Kubernetes ConfigMap instance object.
        key: ConfigMap binary data key.

    Returns:
        Raw bytes for the requested ConfigMap entry.
    """
    config_map_dict = _config_map_as_dict(config_map_instance=config_map_instance)
    binary_data = config_map_dict.get("binaryData") or config_map_dict.get("binary_data") or {}
    if key in binary_data:
        value = binary_data[key]
        if isinstance(value, bytes):
            return value
        return base64.b64decode(s=value)

    data = config_map_dict.get("data") or {}
    if key in data:
        return base64.b64decode(s=data[key])

    raise RuntimeError(f"ConfigMap key '{key}' not found in binaryData or data")
