import logging
import shlex
from subprocess import check_output

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.resource import Resource
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service_account import ServiceAccount
from ocp_resources.ssp import SSP
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pyhelper_utils.shell import run_command
from pytest_testconfig import py_config

from tests.infrastructure.vm_console_proxy.constants import (
    KUBE_SYSTEM_NAMESPACE,
    TOKEN_API_VERSION,
    TOKEN_ENDPOINT,
    VM_CONSOLE_PROXY,
    VM_CONSOLE_PROXY_CLUSTER_ROLE,
    VM_CONSOLE_PROXY_USER,
)
from tests.infrastructure.vm_console_proxy.utils import (
    create_vnc_console_token,
    get_vm_console_proxy_resource,
)
from utilities.constants import OS_FLAVOR_RHEL, TIMEOUT_10MIN, Images
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import login_with_token, login_with_user_password
from utilities.virt import VirtualMachineForTests, wait_for_running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def enabled_vm_console_proxy_spec(hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "deployVmConsoleProxy": True,
                }
            }
        },
        list_resource_reconcile=[SSP],
        wait_for_reconcile_post_update=True,
    ):
        yield
    vm_console_proxy_resources_object = get_vm_console_proxy_resource(
        resource_kind=RoleBinding,
        namespace=KUBE_SYSTEM_NAMESPACE,
    )
    if vm_console_proxy_resources_object.exists:
        vm_console_proxy_resources_object.clean_up()
        pytest.fail(
            f"Resource exists: {vm_console_proxy_resources_object.kind}"
            f"/{vm_console_proxy_resources_object.name} under "
            f"{vm_console_proxy_resources_object.namespace}. Forceful Cleanup Done."
        )


@pytest.fixture(scope="class")
def vm_console_proxy_cluster_resource(
    cnv_vm_console_proxy_cluster_resource_matrix__class__,
):
    return get_vm_console_proxy_resource(resource_kind=cnv_vm_console_proxy_cluster_resource_matrix__class__)


@pytest.fixture(scope="class")
def vm_console_proxy_namespace_resource(
    cnv_vm_console_proxy_namespace_resource_matrix__class__,
):
    resource_namespace = (
        KUBE_SYSTEM_NAMESPACE
        if cnv_vm_console_proxy_namespace_resource_matrix__class__ == RoleBinding
        else py_config["hco_namespace"]
    )
    return get_vm_console_proxy_resource(
        resource_kind=cnv_vm_console_proxy_namespace_resource_matrix__class__,
        namespace=resource_namespace,
    )


@pytest.fixture(scope="class")
def vm_for_console_proxy(namespace, unprivileged_client):
    with VirtualMachineForTests(
        name=f"rhel-{VM_CONSOLE_PROXY}",
        image=Images.Rhel.RHEL10_REGISTRY_GUEST_IMG,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(name="u1.small"),
        vm_preference=VirtualMachineClusterPreference(name="rhel.10"),
        os_flavor=OS_FLAVOR_RHEL,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        wait_for_running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def vm_console_proxy_service_account(namespace):
    with ServiceAccount(name=f"{VM_CONSOLE_PROXY_USER}1", namespace=namespace.name) as sa:
        yield sa


@pytest.fixture(scope="class")
def vm_service_account_role_binding(namespace, vm_console_proxy_service_account):
    with RoleBinding(
        name=f"{VM_CONSOLE_PROXY_USER}",
        namespace=namespace.name,
        subjects_kind=vm_console_proxy_service_account.kind,
        subjects_name=vm_console_proxy_service_account.name,
        subjects_namespace=namespace.name,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=f"{Resource.ApiGroup.KUBEVIRT_IO}:admin",
    ) as vm_service_account_role_binding:
        yield vm_service_account_role_binding


@pytest.fixture(scope="class")
def vm_console_proxy_cluster_role_exists():
    assert ClusterRole(name=VM_CONSOLE_PROXY_CLUSTER_ROLE).exists, (
        f"ClusterRole {VM_CONSOLE_PROXY_CLUSTER_ROLE} not found"
    )


@pytest.fixture(scope="class")
def vm_console_proxy_service_account_role_binding(
    namespace, vm_console_proxy_cluster_role_exists, vm_console_proxy_service_account
):
    with RoleBinding(
        name=f"{VM_CONSOLE_PROXY_USER}-token-access",
        namespace=namespace.name,
        subjects_kind=vm_console_proxy_service_account.kind,
        subjects_name=vm_console_proxy_service_account.name,
        subjects_namespace=namespace.name,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=VM_CONSOLE_PROXY_CLUSTER_ROLE,
    ) as vm_role_service_account_role_binding:
        yield vm_role_service_account_role_binding


@pytest.fixture(scope="class")
def generated_service_account_token(vm_console_proxy_service_account):
    # Token creation time can't be less than 10m. This is kubernetes limitation
    return run_command(
        command=shlex.split(
            f"oc create token -n {vm_console_proxy_service_account.namespace} "
            f"{vm_console_proxy_service_account.name} --duration={TIMEOUT_10MIN}s"
        ),
    )[1]


@pytest.fixture(scope="class")
def generated_vnc_access_token(admin_client, vm_for_console_proxy, generated_service_account_token):
    # Token creation time can't be less than 10m. This is kubernetes limitation
    return create_vnc_console_token(
        url=admin_client.configuration.host,
        endpoint=TOKEN_ENDPOINT,
        api_version=TOKEN_API_VERSION,
        namespace=vm_for_console_proxy.namespace,
        virtual_machine=vm_for_console_proxy.name,
        duration=f"{TIMEOUT_10MIN}s",
        runtime_headers={"Authorization": f"Bearer {generated_service_account_token}"},
    )


@pytest.fixture(scope="class")
def logged_with_token(admin_client, generated_vnc_access_token):
    current_user = check_output("oc whoami", shell=True).decode().strip()
    login_with_token(api_address=admin_client.configuration.host, token=generated_vnc_access_token)
    yield
    login_with_user_password(
        api_address=admin_client.configuration.host,
        user=current_user.strip(),
    )
