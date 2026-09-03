"""
Pytest conftest file for CNV Storage snapshots tests
"""

import logging
import shlex
from time import monotonic

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.storage.snapshots.constants import NUM_MULTI_DISK_VMS, WINDOWS_DIRECTORY_PATH
from tests.storage.snapshots.utils import (
    create_vm_with_4_disks,
    raise_cleanup_failures,
    restore_vm_within_deadline,
    run_parallel,
)
from tests.storage.utils import (
    assert_windows_directory_existence,
    create_windows_directory,
    set_permissions,
)
from tests.utils import create_windows2022_vm
from utilities.constants.architecture import AMD_64
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL
from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
)
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def permissions_for_dv(namespace, admin_client):
    """
    Sets DV permissions for an unprivileged client
    """
    with set_permissions(
        client=admin_client,
        role_name="datavolume-cluster-role",
        role_api_groups=[DataVolume.api_group],
        verbs=["*"],
        permissions_to_resources=["datavolumes", "datavolumes/source"],
        binding_name="role-bind-data-volume",
        namespace=namespace.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RoleBinding.api_group,
    ):
        yield


@pytest.fixture()
def windows_vm_with_vtpm_for_snapshot(
    request,
    namespace,
    unprivileged_client,
    modern_cpu_for_migration,
    windows_validation_os_images_data_source_scope_session,
    storage_class_matrix_snapshot_matrix__module__,
):
    with create_windows2022_vm(
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows_validation_os_images_data_source_scope_session,
            storage_class=next(iter(storage_class_matrix_snapshot_matrix__module__)),
        ),
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name=request.param["vm_name"],
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        yield vm


@pytest.fixture()
def snapshot_windows_directory(windows_vm_with_vtpm_for_snapshot):
    create_windows_directory(windows_vm=windows_vm_with_vtpm_for_snapshot, directory_path=WINDOWS_DIRECTORY_PATH)


@pytest.fixture()
def windows_snapshot(
    snapshot_windows_directory,
    windows_vm_with_vtpm_for_snapshot,
):
    with VirtualMachineSnapshot(
        name="windows-snapshot",
        namespace=windows_vm_with_vtpm_for_snapshot.namespace,
        vm_name=windows_vm_with_vtpm_for_snapshot.name,
        client=windows_vm_with_vtpm_for_snapshot.client,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def snapshot_dirctory_removed(windows_vm_with_vtpm_for_snapshot, windows_snapshot):
    windows_snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)
    cmd = shlex.split(
        f'powershell -command "Remove-Item -Path {WINDOWS_DIRECTORY_PATH} -Recurse"',
    )
    run_ssh_commands(
        host=windows_vm_with_vtpm_for_snapshot.ssh_exec, commands=cmd, wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_5SEC
    )
    assert_windows_directory_existence(
        expected_result=False,
        windows_vm=windows_vm_with_vtpm_for_snapshot,
        directory_path=WINDOWS_DIRECTORY_PATH,
    )
    windows_vm_with_vtpm_for_snapshot.stop(wait=True)


@pytest.fixture()
def file_created_during_snapshot(windows_vm_with_vtpm_for_snapshot, windows_snapshot):
    file = f"{WINDOWS_DIRECTORY_PATH}\\file.txt"
    cmd = shlex.split(
        f'powershell -command "for($i=1; $i -le 100; $i++){{$i| Out-File -FilePath {file} -Append}}"',
    )
    run_ssh_commands(
        host=windows_vm_with_vtpm_for_snapshot.ssh_exec, commands=cmd, wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_5SEC
    )
    windows_snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
    windows_vm_with_vtpm_for_snapshot.stop(wait=True)


@pytest.fixture()
def source_volume_name_for_predictable_name_restore(rhel_vm_for_snapshot):
    yield next(
        volume.name
        for volume in rhel_vm_for_snapshot.instance.spec.template.spec.volumes
        if getattr(volume, "dataVolume", None) or getattr(volume, "persistentVolumeClaim", None)
    )


@pytest.fixture()
def vm_restore_with_predictable_names(
    admin_client,
    rhel_vm_for_snapshot,
    snapshot_with_content,
):
    if rhel_vm_for_snapshot.ready:
        rhel_vm_for_snapshot.stop(wait=True)

    with VirtualMachineRestore(
        name=f"{rhel_vm_for_snapshot.name}-restored",
        namespace=rhel_vm_for_snapshot.namespace,
        vm_name=rhel_vm_for_snapshot.name,
        snapshot_name=snapshot_with_content[0].name,
        client=admin_client,
        volume_restore_policy="PrefixTargetName",
    ) as vm_restore:
        vm_restore.wait_restore_done(timeout=TIMEOUT_10MIN)
        yield vm_restore


@pytest.fixture()
def created_vm_with_4_disks_for_snapshot(
    unprivileged_client,
    namespace,
    snapshot_storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """Deploy a Fedora VM with four disk devices for snapshot restore testing.

    Yields:
        VirtualMachineForTests: Deployed VM with four disk devices, not yet confirmed Running.
    """
    cpu_arch = py_config["cpu_arch"]
    preference_name = f"{OS_FLAVOR_FEDORA}.{cpu_arch}" if cpu_arch and cpu_arch != AMD_64 else OS_FLAVOR_FEDORA
    vm = create_vm_with_4_disks(
        vm_name="vm-restore-4-disks",
        namespace_name=namespace.name,
        client=unprivileged_client,
        storage_class_name=snapshot_storage_class_name_scope_module,
        data_source=fedora_data_source_scope_module,
        vm_instance_type=VirtualMachineClusterInstancetype(
            name=U1_SMALL, client=unprivileged_client, ensure_exists=True
        ),
        vm_preference=VirtualMachineClusterPreference(
            name=preference_name, client=unprivileged_client, ensure_exists=True
        ),
    )
    try:
        yield vm
    finally:
        try:
            vm.clean_up()
        except Exception as cleanup_error:
            raise_cleanup_failures(message="VM cleanup failures", cleanup_errors=[cleanup_error])


@pytest.fixture()
def vm_with_4_disks_for_snapshot(created_vm_with_4_disks_for_snapshot):
    """Wait for the 4-disk VM to reach Running with SSH connectivity.

    Yields:
        VirtualMachineForTests: Running VM with four disk devices.
    """
    LOGGER.info(f"Waiting for VM {created_vm_with_4_disks_for_snapshot.name} to reach Running")
    running_vm(vm=created_vm_with_4_disks_for_snapshot)
    yield created_vm_with_4_disks_for_snapshot


@pytest.fixture()
def snapshot_of_vm_with_4_disks(admin_client, vm_with_4_disks_for_snapshot):
    """Create an offline snapshot of the 4-disk VM.

    Yields:
        VirtualMachineSnapshot: Completed snapshot of the 4-disk VM.
    """
    LOGGER.info(f"Stopping VM {vm_with_4_disks_for_snapshot.name} for snapshot")
    vm_with_4_disks_for_snapshot.stop(wait=True)
    snapshot = VirtualMachineSnapshot(
        name=f"snapshot-{vm_with_4_disks_for_snapshot.name}",
        namespace=vm_with_4_disks_for_snapshot.namespace,
        vm_name=vm_with_4_disks_for_snapshot.name,
        client=admin_client,
    )
    try:
        LOGGER.info(f"Creating snapshot {snapshot.name}")
        snapshot.deploy()
        LOGGER.info(f"Waiting for snapshot {snapshot.name} to complete")
        snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
        yield snapshot
    finally:
        try:
            snapshot.clean_up()
        except Exception as cleanup_error:
            raise_cleanup_failures(message="Snapshot cleanup failures", cleanup_errors=[cleanup_error])


@pytest.fixture()
def created_four_vms_with_4_disks_for_snapshot(
    unprivileged_client,
    namespace,
    snapshot_storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """Deploy four Fedora VMs for concurrent snapshot restore testing.

    Yields:
        list: Deployed VirtualMachineForTests objects, each with four disk devices.

    Raises:
        ExceptionGroup: If cleanup of one or more VMs fails. Includes the original
            setup or test failure when both occur.
    """
    cpu_arch = py_config["cpu_arch"]
    preference_name = f"{OS_FLAVOR_FEDORA}.{cpu_arch}" if cpu_arch and cpu_arch != AMD_64 else OS_FLAVOR_FEDORA
    instance_type = VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client, ensure_exists=True)
    preference = VirtualMachineClusterPreference(name=preference_name, client=unprivileged_client, ensure_exists=True)

    vms = []
    try:
        vms, create_errors = run_parallel(
            items=list(range(NUM_MULTI_DISK_VMS)),
            func=lambda vm_index: create_vm_with_4_disks(
                vm_name=f"vm-restore-4d-{vm_index}",
                namespace_name=namespace.name,
                client=unprivileged_client,
                storage_class_name=snapshot_storage_class_name_scope_module,
                data_source=fedora_data_source_scope_module,
                vm_instance_type=instance_type,
                vm_preference=preference,
            ),
            label="Failed to create VM",
            item_name=lambda vm_index: f"vm-restore-4d-{vm_index}",
        )
        if create_errors:
            raise ExceptionGroup("VM creation failures", create_errors)
        yield vms
    finally:
        _, cleanup_errors = run_parallel(
            items=vms,
            func=lambda vm: vm.clean_up(),
            label="Failed to clean up VM",
            item_name=lambda vm: vm.name,
        )
        raise_cleanup_failures(message="VM cleanup failures", cleanup_errors=cleanup_errors)


@pytest.fixture()
def four_vms_with_4_disks_for_snapshot(created_four_vms_with_4_disks_for_snapshot):
    """Wait for the four 4-disk VMs to reach Running with SSH connectivity.

    Yields:
        list: Running VirtualMachineForTests objects, each with four disk devices.
    """
    LOGGER.info("Waiting for VMs to reach Running")
    _, start_errors = run_parallel(
        items=created_four_vms_with_4_disks_for_snapshot,
        func=lambda vm: running_vm(vm=vm),
        label="Failed to start VM",
        item_name=lambda vm: vm.name,
    )
    if start_errors:
        raise ExceptionGroup("VM start failures", start_errors)
    yield created_four_vms_with_4_disks_for_snapshot


@pytest.fixture()
def snapshots_of_four_vms(admin_client, four_vms_with_4_disks_for_snapshot):
    """Create offline snapshots of all four VMs.

    Yields:
        dict: Mapping of each VM to its completed VirtualMachineSnapshot.

    Raises:
        ExceptionGroup: If cleanup of one or more snapshots fails. Includes the original
            setup or test failure when both occur.
    """
    LOGGER.info("Stopping VMs for snapshot")
    _, stop_errors = run_parallel(
        items=four_vms_with_4_disks_for_snapshot,
        func=lambda vm: vm.stop(wait=True),
        label="Failed to stop VM",
        item_name=lambda vm: vm.name,
    )
    if stop_errors:
        raise ExceptionGroup("VM stop failures", stop_errors)

    snapshots = [
        VirtualMachineSnapshot(
            name=f"snapshot-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
            client=admin_client,
        )
        for vm in four_vms_with_4_disks_for_snapshot
    ]
    try:
        LOGGER.info("Creating snapshots")
        _, deploy_errors = run_parallel(
            items=snapshots,
            func=lambda snapshot: snapshot.deploy(),
            label="Failed to create snapshot",
            item_name=lambda snapshot: snapshot.name,
        )
        if deploy_errors:
            raise ExceptionGroup("Snapshot creation failures", deploy_errors)

        LOGGER.info("Waiting for snapshots to complete")
        _, wait_errors = run_parallel(
            items=snapshots,
            func=lambda snapshot: snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN),
            label="Failed to complete snapshot",
            item_name=lambda snapshot: snapshot.name,
        )
        if wait_errors:
            raise ExceptionGroup("Snapshot wait failures", wait_errors)

        yield dict(zip(four_vms_with_4_disks_for_snapshot, snapshots))
    finally:
        _, cleanup_errors = run_parallel(
            items=snapshots,
            func=lambda snapshot: snapshot.clean_up(),
            label="Failed to clean up snapshot",
            item_name=lambda snapshot: snapshot.name,
        )
        raise_cleanup_failures(message="Snapshot cleanup failures", cleanup_errors=cleanup_errors)


@pytest.fixture()
def restored_vm_with_4_disks(admin_client, vm_with_4_disks_for_snapshot, snapshot_of_vm_with_4_disks):
    """Restore the 4-disk VM snapshot within the 5-minute performance budget.

    Yields:
        VirtualMachineRestore: Completed restore of the 4-disk VM.
    """
    vm_restore = VirtualMachineRestore(
        name=f"restore-{vm_with_4_disks_for_snapshot.name}",
        namespace=vm_with_4_disks_for_snapshot.namespace,
        vm_name=vm_with_4_disks_for_snapshot.name,
        snapshot_name=snapshot_of_vm_with_4_disks.name,
        client=admin_client,
    )
    deadline = monotonic() + TIMEOUT_5MIN
    try:
        restore_vm_within_deadline(restore=vm_restore, deadline=deadline)
        yield vm_restore
    finally:
        try:
            vm_restore.clean_up()
        except Exception as cleanup_error:
            raise_cleanup_failures(message="Restore cleanup failures", cleanup_errors=[cleanup_error])


@pytest.fixture()
def restored_four_vms(admin_client, snapshots_of_four_vms):
    """Restore all four VM snapshots concurrently, each within its own 5-minute budget.

    Yields:
        list: VirtualMachineRestore objects for the concurrent restores.

    Raises:
        ExceptionGroup: If one or more restores fail, or if restore cleanup fails.
            Cleanup failures include the original restore or test failure when both occur.
    """
    restores = [
        VirtualMachineRestore(
            name=f"restore-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
            snapshot_name=snapshot.name,
            client=admin_client,
        )
        for vm, snapshot in snapshots_of_four_vms.items()
    ]
    try:
        _, restore_errors = run_parallel(
            items=restores,
            func=lambda restore: restore_vm_within_deadline(restore=restore, deadline=monotonic() + TIMEOUT_5MIN),
            label="Failed to restore VM",
            item_name=lambda restore: restore.name,
        )
        if restore_errors:
            raise ExceptionGroup("Restore failures", restore_errors)

        yield restores
    finally:
        _, cleanup_errors = run_parallel(
            items=restores,
            func=lambda restore: restore.clean_up(),
            label="Failed to clean up restore",
            item_name=lambda restore: restore.name,
        )
        raise_cleanup_failures(message="Restore cleanup failures", cleanup_errors=cleanup_errors)
