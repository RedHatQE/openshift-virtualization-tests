"""
VMExport tests
"""

import shlex

import pytest
from kubernetes.client import ApiException
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_export import VirtualMachineExport
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.storage.vm_export.constants import VM_EXPORT_TEST_FILE_CONTENT, VM_EXPORT_TEST_FILE_NAME
from utilities.constants import Images
from utilities.infra import run_virtctl_command
from utilities.virt import running_vm

VIRTUALMACHINEEXPORTS = "virtualmachineexports"
ERROR_MSG_USER_CANNOT_CREATE_VM_EXPORT = (
    rf".*{VIRTUALMACHINEEXPORTS}.{Resource.ApiGroup.EXPORT_KUBEVIRT_IO} is forbidden: User.*cannot create resource"
    rf".*{VIRTUALMACHINEEXPORTS}.*in API group.*{Resource.ApiGroup.EXPORT_KUBEVIRT_IO}.*in the namespace"
)


@pytest.mark.parametrize(
    "namespace, data_volume_scope_function",
    [
        pytest.param(
            {"use_unprivileged_client": False},
            {
                "dv_name": "cirros-dv-9338",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            marks=pytest.mark.polarion("CNV-9338"),
        )
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_fail_to_vmexport_with_unprivileged_client_no_permissions(
    unprivileged_client,
    data_volume_scope_function,
):
    with pytest.raises(
        ApiException,
        match=ERROR_MSG_USER_CANNOT_CREATE_VM_EXPORT,
    ):
        with VirtualMachineExport(
            name="vmexport-unprivileged",
            namespace=data_volume_scope_function.namespace,
            client=unprivileged_client,
            source={
                "apiGroup": "",
                "kind": PersistentVolumeClaim.kind,
                "name": data_volume_scope_function.name,
            },
        ) as vmexport:
            assert not vmexport, "VMExport created by unprivileged client"


@pytest.mark.polarion("CNV-9903")
@pytest.mark.gating()
@pytest.mark.s390x
def test_vmexport_snapshot_manifests(
    vm_from_vmexport,
):
    running_vm(vm=vm_from_vmexport)

    result = run_ssh_commands(host=vm_from_vmexport.ssh_exec, commands=shlex.split(f"cat {VM_EXPORT_TEST_FILE_NAME}"))
    file_content = result[0].strip()

    assert file_content == VM_EXPORT_TEST_FILE_CONTENT


@pytest.mark.s390x
@pytest.mark.polarion("CNV-11597")
def test_virtctl_vmexport_unprivileged(
    vmexport_download_path, blank_dv_created_by_specific_user, virtctl_unprivileged_client
):
    return_code, out, err = run_virtctl_command(
        command=shlex.split(
            f"vmexport download test-pvc-export-unprivileged --pvc={blank_dv_created_by_specific_user.name} "
            f"--output {vmexport_download_path}"
        ),
        namespace=blank_dv_created_by_specific_user.namespace,
        verify_stderr=False,
    )
    assert return_code, f"Failed to run virtctl vmexport by unprivileged user, out: {out}, err: {err}."
