import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.volume_snapshot import VolumeSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.file_level_restore.constants import (
    LINUX_DATA_DISK_MOUNT_PATH,
    LINUX_DATA_DISK_SIZE,
    LINUX_DATA_DISK_SNAPSHOT_RESTORE_CR_NAME,
    LINUX_DATA_DISK_SNAPSHOT_SECOND_RESTORE_CR_NAME,
    LINUX_RESTORE_TEST_DIRECTORY,
    LINUX_ROOT_DISK_PVC_RESTORE_CR_NAME,
    LINUX_ROOT_DISK_SNAPSHOT_RESTORE_CR_NAME,
    LINUX_ROOT_DISK_VM_SNAPSHOT_NAME,
    LINUX_TEST_FILE_CONTENT,
    LINUX_TEST_FILE_CONTENT_2,
    LINUX_TEST_FILE_NAME,
    LINUX_TEST_FILE_NAME_2,
    WINDOWS_DATA_DISK_LETTER,
    WINDOWS_DATA_DISK_SIZE,
    WINDOWS_DRIVE_ROOT_FILE_CONTENT,
    WINDOWS_DRIVE_ROOT_FILE_NAME,
    WINDOWS_MULTI_FILE_COUNT,
    WINDOWS_RESTORE_TEST_DIRECTORY,
    WINDOWS_TEST_FILE_CONTENT,
    WINDOWS_TEST_FILE_NAME,
)
from tests.storage.file_level_restore.utils import (
    VirtualMachineFileRestore,
    delete_linux_data_disk_file,
    delete_linux_guest_file,
    delete_windows_guest_file,
    ensure_linux_data_disk_directory,
    format_and_mount_linux_data_disk,
    get_windows_file_acl_baseline,
    initialize_and_format_windows_data_disk,
    install_linux_guest_helper,
    install_windows_guest_helper,
    linux_data_disk_file_path,
    linux_restore_test_file_path,
    linux_root_disk_online_virtual_machine_snapshot,
    linux_volume_snapshot,
    wait_for_file_restore_operator_ready,
    wait_for_file_restore_phase,
    windows_data_disk_path,
    windows_data_disk_volume_snapshot,
    windows_guest_path,
)
from tests.utils import create_windows2022_vm
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL10_PREFERENCE, U1_SMALL
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC
from utilities.storage import (
    add_dv_to_vm,
    create_dv,
    data_volume_template_with_source_ref_dict,
    virtctl_volume,
    wait_for_vm_volume_ready,
    write_file_via_ssh,
)
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def file_restore_operator(admin_client):
    """Verify the HCO-managed file-restore operator is deployed and ready."""
    wait_for_file_restore_operator_ready(admin_client=admin_client)
    yield


@pytest.fixture(scope="class")
def linux_data_disk(admin_client, namespace, snapshot_storage_class_name_scope_module):
    """Blank DataVolume used as the Linux VM secondary data disk."""
    with DataVolume(
        name="file-restore-linux-data-disk",
        namespace=namespace.name,
        source="blank",
        size=LINUX_DATA_DISK_SIZE,
        storage_class=snapshot_storage_class_name_scope_module,
        client=admin_client,
        api_name="storage",
    ) as data_volume:
        yield data_volume


@pytest.fixture(scope="class")
def file_restore_linux_vm(
    admin_client,
    namespace,
    rhel10_data_source_scope_session,
    snapshot_storage_class_name_scope_module,
    file_restore_operator,
    linux_data_disk,
):
    """Running RHEL10 VM with guest helper and a formatted secondary data disk."""
    with VirtualMachineForTests(
        name="file-restore-linux-vm",
        namespace=namespace.name,
        client=admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(
            client=admin_client,
            name=U1_SMALL,
        ),
        vm_preference=VirtualMachineClusterPreference(
            client=admin_client,
            name=RHEL10_PREFERENCE,
        ),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
    ) as vm:
        add_dv_to_vm(vm=vm, dv_name=linux_data_disk.name)
        running_vm(vm=vm)
        install_linux_guest_helper(vm=vm, admin_client=admin_client)
        format_and_mount_linux_data_disk(
            vm=vm,
            mount_path=LINUX_DATA_DISK_MOUNT_PATH,
            data_disk_name=linux_data_disk.name,
        )
        yield vm


@pytest.fixture()
def file_restore_linux_root_only_vm(
    admin_client,
    namespace,
    rhel10_data_source_scope_session,
    snapshot_storage_class_name_scope_module,
    file_restore_operator,
):
    """Running RHEL10 VM with guest helper and root disk only (no secondary data disk).

    Root-disk tests use online VirtualMachineSnapshot. KubeVirt uses QEMU guest-agent
    fsfreeze to quiesce mounted filesystems before snapshot.
    """
    with VirtualMachineForTests(
        name="file-restore-linux-root-only-vm",
        namespace=namespace.name,
        client=admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(
            client=admin_client,
            name=U1_SMALL,
        ),
        vm_preference=VirtualMachineClusterPreference(
            client=admin_client,
            name=RHEL10_PREFERENCE,
        ),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
    ) as vm:
        running_vm(vm=vm)
        install_linux_guest_helper(vm=vm, admin_client=admin_client)
        yield vm


@pytest.fixture()
def linux_test_file_on_data_disk(file_restore_linux_vm):
    """Test file on the Linux data disk.

    The file is written on the mounted data disk. The backup volume exposes it at the
    volume root using the same relative path. The operator restores to the guest
    filesystem root at that path (targetPath is not supported).

    Yields (restore_path, content).
    """
    restore_path = linux_restore_test_file_path(username=file_restore_linux_vm.username)
    restore_directory, _ = restore_path.rsplit("/", maxsplit=1)
    ensure_linux_data_disk_directory(vm=file_restore_linux_vm, relative_directory=restore_directory)
    data_disk_path = linux_data_disk_file_path(relative_path=restore_path)
    write_file_via_ssh(
        vm=file_restore_linux_vm,
        filename=data_disk_path,
        content=LINUX_TEST_FILE_CONTENT,
    )
    yield restore_path, LINUX_TEST_FILE_CONTENT


@pytest.fixture()
def linux_data_disk_snapshot(
    file_restore_linux_vm,
    linux_test_file_on_data_disk,
    linux_data_disk,
    namespace,
    admin_client,
    snapshot_storage_class_name_scope_module,
):
    """VolumeSnapshot of the Linux data disk PVC containing the test file."""
    with linux_volume_snapshot(
        vm=file_restore_linux_vm,
        pvc_name=linux_data_disk.name,
        snapshot_name="file-restore-linux-data-disk-snapshot",
        namespace_name=namespace.name,
        storage_class_name=snapshot_storage_class_name_scope_module,
        admin_client=admin_client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def linux_test_file_on_root_disk(file_restore_linux_root_only_vm):
    """Test file on the Linux VM root filesystem. Yields (restore_path, content)."""
    restore_path = linux_restore_test_file_path(username=file_restore_linux_root_only_vm.username)
    restore_directory, _ = restore_path.rsplit("/", maxsplit=1)
    run_ssh_commands(
        host=file_restore_linux_root_only_vm.ssh_exec,
        commands=["mkdir", "-p", restore_directory],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    write_file_via_ssh(
        vm=file_restore_linux_root_only_vm,
        filename=restore_path,
        content=LINUX_TEST_FILE_CONTENT,
    )
    yield restore_path, LINUX_TEST_FILE_CONTENT


@pytest.fixture()
def linux_root_disk_snapshot(
    file_restore_linux_root_only_vm,
    linux_test_file_on_root_disk,
    namespace,
    admin_client,
):
    """Root-disk VolumeSnapshot from an online VirtualMachineSnapshot containing the test file."""
    restore_path, file_content = linux_test_file_on_root_disk
    with linux_root_disk_online_virtual_machine_snapshot(
        vm=file_restore_linux_root_only_vm,
        vm_snapshot_name=LINUX_ROOT_DISK_VM_SNAPSHOT_NAME,
        namespace_name=namespace.name,
        admin_client=admin_client,
        restore_path=restore_path,
        expected_content=file_content,
    ) as vm_snapshot_info:
        yield VolumeSnapshot(
            name=vm_snapshot_info.root_volume_snapshot_name,
            namespace=namespace.name,
            client=admin_client,
        )


@pytest.fixture()
def linux_root_disk_backup_pvc(
    linux_root_disk_snapshot, namespace, admin_client, snapshot_storage_class_name_scope_module
):
    """Backup PVC cloned from the Linux root disk VolumeSnapshot."""
    LOGGER.info(f"Creating Linux root disk backup PVC from VolumeSnapshot '{linux_root_disk_snapshot.name}'")
    with DataVolume(
        name="file-restore-linux-root-backup-pvc",
        namespace=namespace.name,
        source_dict={"snapshot": {"name": linux_root_disk_snapshot.name, "namespace": namespace.name}},
        api_name="storage",
        storage_class=snapshot_storage_class_name_scope_module,
        client=admin_client,
    ) as data_volume:
        data_volume.wait_for_dv_success()
        yield data_volume


@pytest.fixture()
def deleted_linux_test_file_on_root_disk(
    file_restore_linux_root_only_vm,
    linux_root_disk_snapshot,
    linux_test_file_on_root_disk,
):
    """Deleted Linux root-disk test file after snapshot. Yields (restore_path, content)."""
    restore_path, file_content = linux_test_file_on_root_disk
    delete_linux_guest_file(vm=file_restore_linux_root_only_vm, guest_path=restore_path)
    yield restore_path, file_content


@pytest.fixture()
def linux_root_disk_snapshot_file_restore(
    admin_client,
    namespace,
    file_restore_linux_root_only_vm,
    linux_root_disk_snapshot,
    deleted_linux_test_file_on_root_disk,
):
    """Succeeded file restore from a Linux root-disk VolumeSnapshot."""
    restore_path, _ = deleted_linux_test_file_on_root_disk
    with VirtualMachineFileRestore(
        name=LINUX_ROOT_DISK_SNAPSHOT_RESTORE_CR_NAME,
        namespace=namespace.name,
        target_vm_name=file_restore_linux_root_only_vm.name,
        source_snapshot_name=linux_root_disk_snapshot.name,
        source_path=restore_path,
        client=admin_client,
    ) as file_restore:
        wait_for_file_restore_phase(
            file_restore=file_restore,
            target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
        )
        yield file_restore


@pytest.fixture()
def deleted_linux_test_file_on_root_disk_from_backup(
    file_restore_linux_root_only_vm,
    linux_root_disk_backup_pvc,
    linux_test_file_on_root_disk,
):
    """Deleted Linux root-disk test file after backup PVC is ready. Yields (restore_path, content)."""
    restore_path, file_content = linux_test_file_on_root_disk
    delete_linux_guest_file(vm=file_restore_linux_root_only_vm, guest_path=restore_path)
    yield restore_path, file_content


@pytest.fixture()
def linux_root_disk_backup_pvc_file_restore(
    admin_client,
    namespace,
    file_restore_linux_root_only_vm,
    linux_root_disk_backup_pvc,
    deleted_linux_test_file_on_root_disk_from_backup,
):
    """Succeeded file restore from a Linux root-disk backup PVC."""
    restore_path, _ = deleted_linux_test_file_on_root_disk_from_backup
    with VirtualMachineFileRestore(
        name=LINUX_ROOT_DISK_PVC_RESTORE_CR_NAME,
        namespace=namespace.name,
        target_vm_name=file_restore_linux_root_only_vm.name,
        source_pvc_name=linux_root_disk_backup_pvc.name,
        source_path=restore_path,
        client=admin_client,
    ) as file_restore:
        wait_for_file_restore_phase(
            file_restore=file_restore,
            target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
        )
        yield file_restore


@pytest.fixture()
def linux_backup_pvc(linux_data_disk_snapshot, namespace, admin_client, snapshot_storage_class_name_scope_module):
    """Backup PVC cloned from the Linux data disk VolumeSnapshot."""
    LOGGER.info(f"Creating backup PVC from VolumeSnapshot '{linux_data_disk_snapshot.name}'")
    with DataVolume(
        name="file-restore-linux-backup-pvc",
        namespace=namespace.name,
        source_dict={"snapshot": {"name": linux_data_disk_snapshot.name, "namespace": namespace.name}},
        api_name="storage",
        storage_class=snapshot_storage_class_name_scope_module,
        client=admin_client,
    ) as data_volume:
        data_volume.wait_for_dv_success()
        yield data_volume


@pytest.fixture()
def deleted_linux_test_file_on_data_disk(
    file_restore_linux_vm,
    linux_backup_pvc,
    linux_test_file_on_data_disk,
):
    """Deleted Linux data-disk test file after backup PVC is ready.

    Yields (restore_path, content) where restore_path is the guest-root path used
    for sourcePath and post-restore verification.
    """
    restore_path, file_content = linux_test_file_on_data_disk
    delete_linux_data_disk_file(vm=file_restore_linux_vm, restore_path=restore_path)
    yield restore_path, file_content


@pytest.fixture(scope="class")
def windows_data_disk(admin_client, namespace, snapshot_storage_class_name_scope_module):
    """Blank DataVolume used as the Windows VM secondary NTFS data disk."""
    with create_dv(
        client=admin_client,
        source="blank",
        dv_name="file-restore-windows-data-disk",
        namespace=namespace.name,
        size=WINDOWS_DATA_DISK_SIZE,
        storage_class=snapshot_storage_class_name_scope_module,
        consume_wffc=False,
    ) as data_volume:
        yield data_volume


@pytest.fixture(scope="class")
def windows_file_restore_vm(
    admin_client,
    namespace,
    windows_validation_os_images_data_source_scope_session,
    snapshot_storage_class_name_scope_module,
    file_restore_operator,
    windows_data_disk,
):
    """Running Windows 2022 VM with guest helper and a formatted NTFS data disk."""
    with create_windows2022_vm(
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows_validation_os_images_data_source_scope_session,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
        namespace=namespace.name,
        client=admin_client,
        vm_name="file-restore-windows-vm",
    ) as vm:
        with virtctl_volume(
            action="add",
            namespace=namespace.name,
            vm_name=vm.name,
            volume_name=windows_data_disk.name,
            persist=True,
        ):
            wait_for_vm_volume_ready(vm=vm, volume_name=windows_data_disk.name)
            install_windows_guest_helper(vm=vm, admin_client=admin_client)
            initialize_and_format_windows_data_disk(vm=vm, drive_letter=WINDOWS_DATA_DISK_LETTER)
            yield vm


@pytest.fixture()
def windows_test_file_on_data_disk(windows_file_restore_vm):
    """Test file on the Windows NTFS data disk. Yields (guest_path, content)."""
    guest_path = windows_data_disk_path(
        relative_path=f"{WINDOWS_RESTORE_TEST_DIRECTORY}/{WINDOWS_TEST_FILE_NAME}",
    )
    powershell_path = windows_guest_path(guest_path=guest_path)
    directory_path = windows_guest_path(
        guest_path=windows_data_disk_path(relative_path=WINDOWS_RESTORE_TEST_DIRECTORY),
    )
    write_command = (
        f"New-Item -ItemType Directory -Path '{directory_path}' -Force | Out-Null;"
        f" Set-Content -LiteralPath '{powershell_path}' -Value '{WINDOWS_TEST_FILE_CONTENT}' -NoNewline"
    )
    run_ssh_commands(
        host=windows_file_restore_vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", write_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    yield guest_path, WINDOWS_TEST_FILE_CONTENT


@pytest.fixture()
def deleted_windows_test_file_for_snapshot(
    windows_file_restore_vm,
    windows_data_disk_snapshot,
    windows_test_file_on_data_disk,
    windows_ntfs_acl_baseline,
):
    """Deleted Windows data-disk test file after snapshot. Yields (guest_path, content)."""
    guest_path, file_content = windows_test_file_on_data_disk
    delete_windows_guest_file(vm=windows_file_restore_vm, guest_path=guest_path)
    yield guest_path, file_content


@pytest.fixture()
def windows_ntfs_acl_baseline(
    windows_file_restore_vm,
    windows_test_file_on_data_disk,
    windows_data_disk_snapshot,
):
    """Recorded NTFS ACL and owner SID for the Windows test file after snapshot.

    Depends on the snapshot fixture so the baseline is captured while the file
    still exists on the guest, before any delete fixture runs.
    """
    guest_path, _ = windows_test_file_on_data_disk
    powershell_path = windows_guest_path(guest_path=guest_path)
    return get_windows_file_acl_baseline(vm=windows_file_restore_vm, file_path=powershell_path)


@pytest.fixture()
def windows_data_disk_snapshot(
    windows_file_restore_vm,
    windows_test_file_on_data_disk,
    windows_data_disk,
    namespace,
    admin_client,
    snapshot_storage_class_name_scope_module,
):
    """VolumeSnapshot of the Windows NTFS data disk PVC."""
    with windows_data_disk_volume_snapshot(
        vm=windows_file_restore_vm,
        pvc_name=windows_data_disk.name,
        snapshot_name="file-restore-windows-data-disk-snapshot",
        namespace_name=namespace.name,
        storage_class_name=snapshot_storage_class_name_scope_module,
        admin_client=admin_client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def windows_backup_pvc(windows_data_disk_snapshot, namespace, admin_client, snapshot_storage_class_name_scope_module):
    """Backup PVC cloned from the Windows data disk VolumeSnapshot."""
    LOGGER.info(f"Creating Windows backup PVC from VolumeSnapshot '{windows_data_disk_snapshot.name}'")
    with DataVolume(
        name="file-restore-windows-backup-pvc",
        namespace=namespace.name,
        source_dict={"snapshot": {"name": windows_data_disk_snapshot.name, "namespace": namespace.name}},
        api_name="storage",
        storage_class=snapshot_storage_class_name_scope_module,
        client=admin_client,
    ) as data_volume:
        data_volume.wait_for_dv_success()
        yield data_volume


@pytest.fixture()
def deleted_windows_test_file_on_data_disk(
    windows_file_restore_vm,
    windows_backup_pvc,
    windows_test_file_on_data_disk,
    windows_ntfs_acl_baseline,
):
    """Deleted Windows data-disk test file after backup exists. Yields (guest_path, content)."""
    guest_path, file_content = windows_test_file_on_data_disk
    delete_windows_guest_file(vm=windows_file_restore_vm, guest_path=guest_path)
    yield guest_path, file_content


@pytest.fixture()
def windows_multi_files_on_data_disk(windows_file_restore_vm):
    """Multiple test files on the Windows NTFS data disk. Yields list of (guest_path, content)."""
    files: list[tuple[str, str]] = []
    restore_test_directory = windows_guest_path(
        guest_path=windows_data_disk_path(relative_path=WINDOWS_RESTORE_TEST_DIRECTORY),
    )
    for file_index in range(1, WINDOWS_MULTI_FILE_COUNT + 1):
        guest_path = windows_data_disk_path(
            relative_path=f"{WINDOWS_RESTORE_TEST_DIRECTORY}/multi-file-{file_index}.txt",
        )
        file_content = f"windows-multi-file-content-{file_index}"
        powershell_path = windows_guest_path(guest_path=guest_path)
        write_command = (
            f"New-Item -ItemType Directory -Path '{restore_test_directory}' -Force | Out-Null;"
            f" Set-Content -LiteralPath '{powershell_path}' -Value '{file_content}' -NoNewline"
        )
        run_ssh_commands(
            host=windows_file_restore_vm.ssh_exec,
            commands=["powershell", "-NoProfile", "-Command", write_command],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
        files.append((guest_path, file_content))
    yield files


@pytest.fixture()
def windows_multi_file_data_disk_snapshot(
    windows_file_restore_vm,
    windows_multi_files_on_data_disk,
    windows_data_disk,
    namespace,
    admin_client,
    snapshot_storage_class_name_scope_module,
):
    """VolumeSnapshot of the Windows data disk containing multiple test files."""
    with windows_data_disk_volume_snapshot(
        vm=windows_file_restore_vm,
        pvc_name=windows_data_disk.name,
        snapshot_name="file-restore-windows-multi-file-snapshot",
        namespace_name=namespace.name,
        storage_class_name=snapshot_storage_class_name_scope_module,
        admin_client=admin_client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def deleted_windows_multi_files_on_data_disk(
    windows_file_restore_vm,
    windows_multi_file_data_disk_snapshot,
    windows_multi_files_on_data_disk,
):
    """Deleted Windows multi-file set after snapshot. Yields list of (guest_path, content)."""
    for guest_path, _ in windows_multi_files_on_data_disk:
        delete_windows_guest_file(vm=windows_file_restore_vm, guest_path=guest_path)
    yield windows_multi_files_on_data_disk


@pytest.fixture()
def windows_drive_root_file_on_data_disk(windows_file_restore_vm):
    """File at a Windows drive root path. Yields (guest_path, content)."""
    guest_path = windows_data_disk_path(relative_path=WINDOWS_DRIVE_ROOT_FILE_NAME)
    powershell_path = windows_guest_path(guest_path=guest_path)
    write_command = (
        f"Set-Content -LiteralPath '{powershell_path}' -Value '{WINDOWS_DRIVE_ROOT_FILE_CONTENT}' -NoNewline"
    )
    run_ssh_commands(
        host=windows_file_restore_vm.ssh_exec,
        commands=["powershell", "-NoProfile", "-Command", write_command],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    yield guest_path, WINDOWS_DRIVE_ROOT_FILE_CONTENT


@pytest.fixture()
def windows_drive_root_data_disk_snapshot(
    windows_file_restore_vm,
    windows_drive_root_file_on_data_disk,
    windows_data_disk,
    namespace,
    admin_client,
    snapshot_storage_class_name_scope_module,
):
    """VolumeSnapshot of the Windows data disk containing a drive-root file."""
    with windows_data_disk_volume_snapshot(
        vm=windows_file_restore_vm,
        pvc_name=windows_data_disk.name,
        snapshot_name="file-restore-windows-drive-root-snapshot",
        namespace_name=namespace.name,
        storage_class_name=snapshot_storage_class_name_scope_module,
        admin_client=admin_client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def deleted_windows_drive_root_file(
    windows_file_restore_vm,
    windows_drive_root_data_disk_snapshot,
    windows_drive_root_file_on_data_disk,
):
    """Deleted Windows drive-root file after snapshot. Yields (guest_path, content)."""
    guest_path, file_content = windows_drive_root_file_on_data_disk
    delete_windows_guest_file(vm=windows_file_restore_vm, guest_path=guest_path)
    yield guest_path, file_content


@pytest.fixture(scope="class")
def linux_two_test_files_on_data_disk(file_restore_linux_vm):
    """Two distinct test files on the Linux data disk. Yields list of (restore_path, content)."""
    files: list[tuple[str, str]] = []
    file_specs = (
        (LINUX_TEST_FILE_NAME, LINUX_TEST_FILE_CONTENT),
        (LINUX_TEST_FILE_NAME_2, LINUX_TEST_FILE_CONTENT_2),
    )
    for file_name, file_content in file_specs:
        restore_path = f"/home/{file_restore_linux_vm.username}/{LINUX_RESTORE_TEST_DIRECTORY}/{file_name}"
        restore_directory, _ = restore_path.rsplit("/", maxsplit=1)
        ensure_linux_data_disk_directory(vm=file_restore_linux_vm, relative_directory=restore_directory)
        data_disk_path = linux_data_disk_file_path(relative_path=restore_path)
        write_file_via_ssh(
            vm=file_restore_linux_vm,
            filename=data_disk_path,
            content=file_content,
        )
        files.append((restore_path, file_content))
    yield files


@pytest.fixture(scope="class")
def linux_data_disk_snapshot_with_two_files(
    file_restore_linux_vm,
    linux_two_test_files_on_data_disk,
    linux_data_disk,
    namespace,
    admin_client,
    snapshot_storage_class_name_scope_module,
):
    """VolumeSnapshot of the Linux data disk containing two test files."""
    with linux_volume_snapshot(
        vm=file_restore_linux_vm,
        pvc_name=linux_data_disk.name,
        snapshot_name="file-restore-linux-two-file-snapshot",
        namespace_name=namespace.name,
        storage_class_name=snapshot_storage_class_name_scope_module,
        admin_client=admin_client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def deleted_first_linux_file_on_data_disk(
    file_restore_linux_vm,
    linux_data_disk_snapshot_with_two_files,
    linux_two_test_files_on_data_disk,
):
    """Deleted first Linux data-disk test file after snapshot. Yields (restore_path, content)."""
    restore_path, file_content = linux_two_test_files_on_data_disk[0]
    delete_linux_data_disk_file(vm=file_restore_linux_vm, restore_path=restore_path)
    yield restore_path, file_content


@pytest.fixture()
def first_linux_data_disk_snapshot_file_restore(
    admin_client,
    namespace,
    file_restore_linux_vm,
    linux_data_disk_snapshot_with_two_files,
    deleted_first_linux_file_on_data_disk,
):
    """Succeeded restore of the first Linux data-disk file."""
    restore_path, _ = deleted_first_linux_file_on_data_disk
    with VirtualMachineFileRestore(
        name=LINUX_DATA_DISK_SNAPSHOT_RESTORE_CR_NAME,
        namespace=namespace.name,
        target_vm_name=file_restore_linux_vm.name,
        source_snapshot_name=linux_data_disk_snapshot_with_two_files.name,
        source_path=restore_path,
        client=admin_client,
    ) as file_restore:
        wait_for_file_restore_phase(
            file_restore=file_restore,
            target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
        )
        yield file_restore


@pytest.fixture()
def deleted_second_linux_file_on_data_disk(
    file_restore_linux_vm,
    linux_data_disk_snapshot_with_two_files,
    linux_two_test_files_on_data_disk,
):
    """Deleted second Linux data-disk test file after snapshot. Yields (restore_path, content)."""
    restore_path, file_content = linux_two_test_files_on_data_disk[1]
    delete_linux_data_disk_file(vm=file_restore_linux_vm, restore_path=restore_path)
    yield restore_path, file_content


@pytest.fixture()
def second_linux_data_disk_snapshot_file_restore(
    admin_client,
    namespace,
    file_restore_linux_vm,
    linux_data_disk_snapshot_with_two_files,
    deleted_second_linux_file_on_data_disk,
):
    """Succeeded restore of the second Linux data-disk file."""
    restore_path, _ = deleted_second_linux_file_on_data_disk
    with VirtualMachineFileRestore(
        name=LINUX_DATA_DISK_SNAPSHOT_SECOND_RESTORE_CR_NAME,
        namespace=namespace.name,
        target_vm_name=file_restore_linux_vm.name,
        source_snapshot_name=linux_data_disk_snapshot_with_two_files.name,
        source_path=restore_path,
        client=admin_client,
    ) as file_restore:
        wait_for_file_restore_phase(
            file_restore=file_restore,
            target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
        )
        yield file_restore
