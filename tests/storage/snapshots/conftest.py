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

from tests.storage.snapshots.constants import WINDOWS_DIRECTORY_PATH
from tests.storage.utils import (
    assert_windows_directory_existence,
    create_windows19_vm,
    create_windows_directory,
    set_permissions,
)
from utilities.constants import TIMEOUT_2MIN, TIMEOUT_5SEC, TIMEOUT_10MIN, UNPRIVILEGED_USER

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
def windows_vm_for_snapshot(
    request,
    namespace,
    unprivileged_client,
    modern_cpu_for_migration,
    storage_class_matrix_snapshot_matrix__module__,
):
    with create_windows19_vm(
        dv_name=request.param["dv_name"],
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name=request.param["vm_name"],
        cpu_model=modern_cpu_for_migration,
        storage_class=[*storage_class_matrix_snapshot_matrix__module__][0],
    ) as vm:
        yield vm


@pytest.fixture()
def snapshot_windows_directory(windows_vm_for_snapshot):
    create_windows_directory(windows_vm=windows_vm_for_snapshot, directory_path=WINDOWS_DIRECTORY_PATH)


@pytest.fixture()
def windows_snapshot(
    snapshot_windows_directory,
    windows_vm_for_snapshot,
):
    with VirtualMachineSnapshot(
        name="windows-snapshot",
        namespace=windows_vm_for_snapshot.namespace,
        vm_name=windows_vm_for_snapshot.name,
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def snapshot_dirctory_removed(windows_vm_for_snapshot, windows_snapshot):
    windows_snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)
    cmd = shlex.split(
        f'powershell -command "Remove-Item -Path {WINDOWS_DIRECTORY_PATH} -Recurse"',
    )
    run_ssh_commands(host=windows_vm_for_snapshot.ssh_exec, commands=cmd, wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_5SEC)
    assert_windows_directory_existence(
        expected_result=False,
        windows_vm=windows_vm_for_snapshot,
        directory_path=WINDOWS_DIRECTORY_PATH,
    )
    windows_vm_for_snapshot.stop(wait=True)


@pytest.fixture()
def file_created_during_snapshot(windows_vm_for_snapshot, windows_snapshot):
    file = f"{WINDOWS_DIRECTORY_PATH}\\file.txt"
    cmd = shlex.split(
        f'powershell -command "for($i=1; $i -le 100; $i++){{$i| Out-File -FilePath {file} -Append}}"',
    )
    run_ssh_commands(host=windows_vm_for_snapshot.ssh_exec, commands=cmd, wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_5SEC)
    windows_snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
    windows_vm_for_snapshot.stop(wait=True)


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
