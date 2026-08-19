"""
Pytest conftest file for CNV Storage snapshots tests
"""

import logging
import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.snapshots.constants import (
    BLANK_DV_SIZE,
    NUM_BLANK_DISKS,
    NUM_MULTI_DISK_VMS,
    WINDOWS_DIRECTORY_PATH,
)
from tests.storage.utils import (
    assert_windows_directory_existence,
    create_windows_directory,
    set_permissions,
)
from tests.utils import create_windows2022_vm
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
)
from utilities.storage import (
    add_dv_to_vm,
    construct_datavolume_source_dict,
    data_volume_template_with_source_ref_dict,
)
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource

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


def _create_vm_with_4_disks(
    vm_name: str,
    namespace_name: str,
    client: DynamicClient,
    storage_class_name: str,
    data_source: DataSource,
) -> VirtualMachineForTests:
    """Create a Fedora VM with 1 boot disk from DataSource + 3 blank DVs.

    Args:
        vm_name: Name for the VM.
        namespace_name: Namespace to deploy the VM into.
        client: Kubernetes client for resource operations.
        storage_class_name: Storage class for boot and blank PVCs.
        data_source: Fedora golden image DataSource for the boot volume.

    Returns:
        Running VirtualMachineForTests with 4 disk devices.
    """
    vm = VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        client=client,
        os_flavor=OS_FLAVOR_FEDORA,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class_name,
        ),
    )
    vm.deploy(wait=True)
    for disk_index in range(NUM_BLANK_DISKS):
        blank_dv = DataVolume(
            name=f"{vm_name}-blank-{disk_index}",
            namespace=namespace_name,
            client=client,
            source_dict=construct_datavolume_source_dict(source="blank"),
            size=BLANK_DV_SIZE,
            storage_class=storage_class_name,
            api_name="storage",
        )
        blank_dv.to_dict()
        blank_dv.res["metadata"].pop("namespace", None)
        add_dv_to_vm(vm=vm, template_dv=blank_dv.res)
    running_vm(vm=vm)
    return vm


@pytest.fixture()
def vm_with_4_disks_for_snapshot(
    unprivileged_client,
    namespace,
    snapshot_storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """Running Fedora VM with 4 disk devices for snapshot restore testing."""
    vm = _create_vm_with_4_disks(
        vm_name="vm-restore-4-disks",
        namespace_name=namespace.name,
        client=unprivileged_client,
        storage_class_name=snapshot_storage_class_name_scope_module,
        data_source=fedora_data_source_scope_module,
    )
    yield vm
    vm.clean_up()


@pytest.fixture()
def snapshot_of_vm_with_4_disks(admin_client, vm_with_4_disks_for_snapshot):
    """Offline snapshot of the 4-disk VM, ready to use."""
    vm_with_4_disks_for_snapshot.stop(wait=True)
    with VirtualMachineSnapshot(
        name=f"snapshot-{vm_with_4_disks_for_snapshot.name}",
        namespace=vm_with_4_disks_for_snapshot.namespace,
        vm_name=vm_with_4_disks_for_snapshot.name,
        client=admin_client,
    ) as snapshot:
        snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
        yield snapshot


@pytest.fixture()
def four_vms_with_4_disks_for_snapshot(
    unprivileged_client,
    namespace,
    snapshot_storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """4 running Fedora VMs, each with 4 disk devices, for concurrent snapshot restore testing."""
    vms = []
    try:
        for vm_index in range(NUM_MULTI_DISK_VMS):
            vm = _create_vm_with_4_disks(
                vm_name=f"vm-restore-4d-{vm_index}",
                namespace_name=namespace.name,
                client=unprivileged_client,
                storage_class_name=snapshot_storage_class_name_scope_module,
                data_source=fedora_data_source_scope_module,
            )
            vms.append(vm)
        yield vms
    finally:
        for vm in vms:
            try:
                vm.clean_up()
            except Exception as error:
                LOGGER.error(f"Failed to clean up VM {vm.name}: {error}")


@pytest.fixture()
def snapshots_of_four_vms(admin_client, four_vms_with_4_disks_for_snapshot):
    """Offline snapshots of all 4 VMs, ready to use."""
    for vm in four_vms_with_4_disks_for_snapshot:
        vm.stop(wait=True)

    snapshots = []
    try:
        for vm in four_vms_with_4_disks_for_snapshot:
            snapshot = VirtualMachineSnapshot(
                name=f"snapshot-{vm.name}",
                namespace=vm.namespace,
                vm_name=vm.name,
                client=admin_client,
            )
            snapshot.deploy()
            snapshots.append(snapshot)

        for snapshot in snapshots:
            snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)

        yield dict(zip(four_vms_with_4_disks_for_snapshot, snapshots))
    finally:
        for snapshot in snapshots:
            try:
                snapshot.clean_up()
            except Exception as error:
                LOGGER.error(f"Failed to clean up snapshot {snapshot.name}: {error}")


@pytest.fixture()
def restored_vm_with_4_disks(admin_client, vm_with_4_disks_for_snapshot, snapshot_of_vm_with_4_disks):
    """Restore the 4-disk VM snapshot within the 5-minute performance budget."""
    with VirtualMachineRestore(
        name=f"restore-{vm_with_4_disks_for_snapshot.name}",
        namespace=vm_with_4_disks_for_snapshot.namespace,
        vm_name=vm_with_4_disks_for_snapshot.name,
        snapshot_name=snapshot_of_vm_with_4_disks.name,
        client=admin_client,
    ) as vm_restore:
        vm_restore.wait_restore_done(timeout=TIMEOUT_5MIN)
        yield vm_restore


@pytest.fixture()
def restored_four_vms(admin_client, four_vms_with_4_disks_for_snapshot, snapshots_of_four_vms):
    """Restore all 4 VM snapshots concurrently within the 5-minute performance budget."""
    restores = []

    def _restore_vm(vm_and_snapshot: tuple) -> VirtualMachineRestore:
        vm, snapshot = vm_and_snapshot
        restore = VirtualMachineRestore(
            name=f"restore-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
            snapshot_name=snapshot.name,
            client=admin_client,
        )
        restore.deploy()
        restore.wait_restore_done(timeout=TIMEOUT_5MIN)
        return restore

    try:
        with ThreadPoolExecutor(max_workers=NUM_MULTI_DISK_VMS) as executor:
            futures = {
                executor.submit(_restore_vm, (vm, snapshot)): vm for vm, snapshot in snapshots_of_four_vms.items()
            }
            for future in as_completed(futures):
                vm = futures[future]
                try:
                    restores.append(future.result())
                except Exception as error:
                    LOGGER.error(f"Failed to restore VM {vm.name}: {error}")
                    raise

        yield restores
    finally:
        for restore in restores:
            try:
                restore.clean_up()
            except Exception as error:
                LOGGER.error(f"Failed to clean up restore {restore.name}: {error}")
