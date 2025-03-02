# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage snapshots tests
"""

import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.snapshots.constants import WINDOWS_DIRECTORY_PATH
from tests.storage.snapshots.utils import assert_directory_existence
from tests.storage.utils import create_windows19_vm, set_permissions
from utilities.constants import TIMEOUT_10MIN, UNPRIVILEGED_USER

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def permissions_for_dv(namespace):
    """
    Sets DV permissions for an unprivileged client
    """
    with set_permissions(
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
    cmd = shlex.split(
        f'powershell -command "New-Item -Path {WINDOWS_DIRECTORY_PATH} -ItemType Directory"',
    )
    run_ssh_commands(host=windows_vm_for_snapshot.ssh_exec, commands=cmd)
    assert_directory_existence(
        expected_result=True,
        windows_vm=windows_vm_for_snapshot,
        directory_path=WINDOWS_DIRECTORY_PATH,
    )


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
    run_ssh_commands(host=windows_vm_for_snapshot.ssh_exec, commands=cmd)
    assert_directory_existence(
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
    run_ssh_commands(host=windows_vm_for_snapshot.ssh_exec, commands=cmd)
    windows_snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
    windows_vm_for_snapshot.stop(wait=True)
