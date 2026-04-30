# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV Storage snapshots tests
"""

import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.snapshots.constants import WINDOWS_DIRECTORY_PATH
from tests.storage.utils import (
    assert_windows_directory_existence,
    create_windows_directory,
    set_permissions,
)
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.constants import (
    OS_FLAVOR_WINDOWS,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    U1_LARGE,
    UNPRIVILEGED_USER,
    WINDOWS_2K22_PREFERENCE,
    Images,
)
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_windows_vm

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
    storage_class_matrix_snapshot_matrix__module__,
):
    artifactory_secret = get_artifactory_secret(namespace=namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace.name)
    dv = DataVolume(
        name=request.param["dv_name"],
        namespace=namespace.name,
        storage_class=[*storage_class_matrix_snapshot_matrix__module__][0],
        source="http",
        url=get_http_image_url(image_directory=Images.Windows.DIR, image_name=Images.Windows.WIN2022_IMG),
        size=Images.Windows.DEFAULT_DV_SIZE,
        client=unprivileged_client,
        api_name="storage",
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()
    with VirtualMachineForTests(
        name=request.param["vm_name"],
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_WINDOWS,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_LARGE, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=WINDOWS_2K22_PREFERENCE, client=unprivileged_client),
        data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        wait_for_windows_vm(vm=vm, version="2022")
        yield vm
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


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
