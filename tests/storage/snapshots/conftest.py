"""
Pytest conftest file for CNV Storage snapshots tests
"""

import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.constants import NUM_BLANK_DISKS
from tests.storage.snapshots.constants import NUM_MULTI_DISK_VMS, WINDOWS_DIRECTORY_PATH
from tests.storage.utils import (
    VMWithSeveralBlankDisks,
    assert_windows_directory_existence,
    create_windows_directory,
    set_permissions,
)
from tests.utils import create_windows2022_vm
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import (
    TIMEOUT_2MIN,
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
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name=request.param["vm_name"],
        cpu_model=modern_cpu_for_migration,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows_validation_os_images_data_source_scope_session,
            storage_class=next(iter(storage_class_matrix_snapshot_matrix__module__)),
        ),
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
def vm_with_4_disks(
    skip_if_no_storage_class_for_snapshot,
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    snapshot_storage_class_name_scope_module,
):
    """Fedora VM with 1 golden-image boot disk and 3 blank data disks.

    Yields:
        VirtualMachineForTests: Running 4-disk Fedora VM with SSH connectivity.
    """

    with VMWithSeveralBlankDisks(
        name="fedora-4-disks",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        blank_disk_storage_class_name=snapshot_storage_class_name_scope_module,
        num_blank_disks=NUM_BLANK_DISKS,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
        vm_instance_type_infer=True,
        vm_preference_infer=True,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vms_with_4_disks_created(
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    snapshot_storage_class_name_scope_module,
):
    """Create Fedora VMs with 1 boot disk + 3 blank data disks each.

    Yields:
        list[VirtualMachineForTests]: Deployed VMs with 4 disks each (count from NUM_MULTI_DISK_VMS).
    """
    vms = []
    try:
        for vm_index in range(NUM_MULTI_DISK_VMS):
            vm = VMWithSeveralBlankDisks(
                name=f"vm-4disk-{vm_index}",
                namespace=namespace.name,
                client=unprivileged_client,
                os_flavor=OS_FLAVOR_FEDORA,
                blank_disk_storage_class_name=snapshot_storage_class_name_scope_module,
                num_blank_disks=NUM_BLANK_DISKS,
                data_volume_template=data_volume_template_with_source_ref_dict(
                    data_source=fedora_data_source_scope_module,
                    storage_class=snapshot_storage_class_name_scope_module,
                ),
                vm_instance_type_infer=True,
                vm_preference_infer=True,
            )
            vm.deploy(wait=True)
            vms.append(vm)

        yield vms
    finally:
        cleanup_errors = []
        for vm in vms:
            try:
                vm.clean_up()
            except Exception as error:
                LOGGER.error(f"Failed to clean up {vm.name}: {error}")
                cleanup_errors.append(error)

        if cleanup_errors:
            raise ExceptionGroup("VM cleanup errors", cleanup_errors)
