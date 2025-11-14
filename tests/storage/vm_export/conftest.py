"""
Pytest conftest file for CNV VMExport tests
"""

import base64
import shlex
from subprocess import check_output

import pytest
from ocp_resources.config_map import ConfigMap
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from ocp_resources.virtual_machine_export import VirtualMachineExport
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.vm_export.constants import VM_EXPORT_TEST_FILE_CONTENT, VM_EXPORT_TEST_FILE_NAME
from tests.storage.vm_export.utils import create_blank_dv_by_specific_user, get_manifest_from_vmexport, get_manifest_url
from utilities.constants import OS_FLAVOR_RHEL, U1_SMALL, UNPRIVILEGED_PASSWORD, UNPRIVILEGED_USER
from utilities.infra import create_ns, login_with_user_password
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture()
def vmexport_from_vmsnapshot(
    unprivileged_client,
    rhel_vm_snapshot_with_content,
):
    with VirtualMachineExport(
        name="vmexport-from-snapshot",
        namespace=rhel_vm_snapshot_with_content.namespace,
        client=unprivileged_client,
        source={
            "apiGroup": VirtualMachineSnapshot.api_group,
            "kind": VirtualMachineSnapshot.kind,
            "name": rhel_vm_snapshot_with_content.name,
        },
    ) as vmexport:
        vmexport.wait_for_status(status=VirtualMachineExport.Status.READY)
        yield vmexport


@pytest.fixture()
def vmexport_from_vmsnapshot_external_links(vmexport_from_vmsnapshot):
    yield vmexport_from_vmsnapshot.instance.status.links.external


@pytest.fixture()
def token_for_vmexport_from_vmsnapshot(vmexport_from_vmsnapshot):
    secret_name = f"export-token-{vmexport_from_vmsnapshot.name}"
    secret_object = Secret(name=secret_name, namespace=vmexport_from_vmsnapshot.namespace)
    assert secret_object.exists, f"Secret: '{secret_name}' not found"
    token_data = secret_object.instance.get("data", {}).get("token")
    assert token_data, f"No token in Secret {secret_name}"
    return base64.b64decode(s=token_data).decode(encoding="utf-8")


@pytest.fixture()
def vmexport_external_cert_file(tmpdir, vmexport_from_vmsnapshot, vmexport_from_vmsnapshot_external_links):
    ca_cert_path = f"{tmpdir}/cacert.crt"
    cert = vmexport_from_vmsnapshot_external_links.get("cert")
    assert cert, f"External cert in vmexport {vmexport_from_vmsnapshot.name} not found"
    with open(ca_cert_path, "w") as ca_cert_file:
        ca_cert_file.write(cert)
    yield ca_cert_path


@pytest.fixture()
def secret_headers_for_vmexport_from_vmsnapshot(
    vmexport_from_vmsnapshot,
    vmexport_from_vmsnapshot_external_links,
    vmexport_external_cert_file,
    token_for_vmexport_from_vmsnapshot,
    namespace_vmexport_target,
):
    secret_manifest_url = get_manifest_url(
        vmexport_external_links=vmexport_from_vmsnapshot_external_links,
        manifest_type="auth-header-secret",
    )
    secret_yaml_file = get_manifest_from_vmexport(
        vmexport_cert_file=vmexport_external_cert_file,
        url=secret_manifest_url,
        token=token_for_vmexport_from_vmsnapshot,
        kind=Secret.kind,
    )
    with Secret(yaml_file=secret_yaml_file, namespace=namespace_vmexport_target.name):
        yield


@pytest.fixture(scope="module")
def namespace_vmexport_target(admin_client):
    yield from create_ns(admin_client=admin_client, name="vm-export-test-target")


@pytest.fixture()
def vmexport_from_vmsnapshot_manifest_url(vmexport_from_vmsnapshot_external_links):
    yield get_manifest_url(
        vmexport_external_links=vmexport_from_vmsnapshot_external_links,
        manifest_type="all",
    )


@pytest.fixture()
def configmap_with_vmexport_external_cert_vmsnapshot(
    vmexport_external_cert_file,
    vmexport_from_vmsnapshot_manifest_url,
    token_for_vmexport_from_vmsnapshot,
    namespace_vmexport_target,
):
    configmap_yaml_file = get_manifest_from_vmexport(
        vmexport_cert_file=vmexport_external_cert_file,
        url=vmexport_from_vmsnapshot_manifest_url,
        token=token_for_vmexport_from_vmsnapshot,
        kind=ConfigMap.kind,
    )
    with ConfigMap(yaml_file=configmap_yaml_file, namespace=namespace_vmexport_target.name) as router_cert_configmap:
        yield router_cert_configmap


@pytest.fixture()
def vm_from_vmexport(
    vmexport_external_cert_file,
    vmexport_from_vmsnapshot_manifest_url,
    token_for_vmexport_from_vmsnapshot,
    namespace_vmexport_target,
    configmap_with_vmexport_external_cert_vmsnapshot,
    secret_headers_for_vmexport_from_vmsnapshot,
):
    vm_yaml_file = get_manifest_from_vmexport(
        vmexport_cert_file=vmexport_external_cert_file,
        url=vmexport_from_vmsnapshot_manifest_url,
        token=token_for_vmexport_from_vmsnapshot,
        kind=VirtualMachine.kind,
        namespace_vmexport_target=namespace_vmexport_target.name,
    )
    with VirtualMachineForTests(
        name="target-vm",
        namespace=namespace_vmexport_target.name,
        os_flavor=OS_FLAVOR_RHEL,
        yaml_file=vm_yaml_file,
    ) as target_vm:
        yield target_vm


@pytest.fixture()
def blank_dv_created_by_unprivileged_user(namespace, unprivileged_client):
    with create_blank_dv_by_specific_user(
        client=unprivileged_client,
        namespace_name=namespace.name,
        dv_name="blank-dv-by-unprivileged-user",
    ) as dv:
        yield dv


@pytest.fixture()
def blank_dv_created_by_admin_user(namespace, admin_client):
    with create_blank_dv_by_specific_user(
        client=admin_client,
        namespace_name=namespace.name,
        dv_name="blank-dv-by-admin-user",
    ) as dv:
        yield dv


@pytest.fixture()
def virtctl_unprivileged_client(admin_client):
    current_user = check_output("oc whoami", shell=True).decode().strip()
    login_with_user_password(
        api_address=admin_client.configuration.host,
        user=UNPRIVILEGED_USER,
        password=UNPRIVILEGED_PASSWORD,
    )
    yield
    login_with_user_password(
        api_address=admin_client.configuration.host,
        user=current_user,
    )


@pytest.fixture()
def vmexport_download_path(tmp_path):
    temp_path = tmp_path / "test_virtctl_vmexport_unprivileged"
    temp_path.mkdir()
    yield str(temp_path / "disk.img")


@pytest.fixture()
def rhel_vm_for_snapshot_with_content(
    unprivileged_client,
    namespace,
    rhel10_data_source_scope_session,
    snapshot_storage_class_name_scope_module,
):
    with VirtualMachineForTests(
        name="rhel-vm-for-snapshot",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name="rhel.10"),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
    ) as vm:
        running_vm(vm=vm)

        cmd = shlex.split(f"echo '{VM_EXPORT_TEST_FILE_CONTENT}' > {VM_EXPORT_TEST_FILE_NAME} && sync")
        run_ssh_commands(host=vm.ssh_exec, commands=cmd)

        yield vm


@pytest.fixture()
def rhel_vm_snapshot_with_content(
    unprivileged_client,
    rhel_vm_for_snapshot_with_content,
):
    with VirtualMachineSnapshot(
        name=f"snapshot-{rhel_vm_for_snapshot_with_content.name}",
        namespace=rhel_vm_for_snapshot_with_content.namespace,
        vm_name=rhel_vm_for_snapshot_with_content.name,
        client=unprivileged_client,
    ) as vm_snapshot:
        vm_snapshot.wait_snapshot_done()
        yield vm_snapshot
