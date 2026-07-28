import pytest
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine import VirtualMachine

from tests.install_upgrade_operators.role_aggregation.utils import (
    disable_aggregation_and_wait,
    ensure_aggregation_enabled,
    wait_for_vm_list_access,
)
from utilities.constants.pytest import UNPRIVILEGED_USER


@pytest.fixture(scope="module")
def admin_role_binding(admin_client, namespace):
    """RoleBinding granting admin ClusterRole to the unprivileged user."""
    with RoleBinding(
        name="test-role-bind-admin",
        namespace=namespace.name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace.name,
        role_ref_kind="ClusterRole",
        role_ref_name="admin",
    ):
        yield


@pytest.fixture(scope="module")
def edit_role_binding(admin_client, namespace):
    """RoleBinding granting edit ClusterRole to the unprivileged user."""
    with RoleBinding(
        name="test-role-bind-edit",
        namespace=namespace.name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace.name,
        role_ref_kind="ClusterRole",
        role_ref_name="edit",
    ):
        yield


@pytest.fixture(scope="module")
def view_role_binding(admin_client, namespace):
    """RoleBinding granting view ClusterRole to the unprivileged user."""
    with RoleBinding(
        name="test-role-bind-view",
        namespace=namespace.name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace.name,
        role_ref_kind="ClusterRole",
        role_ref_name="view",
    ):
        yield


@pytest.fixture()
def disabled_aggregation_state(
    request,
    admin_client,
    unprivileged_client,
    namespace,
    hyperconverged_resource_scope_module,
):
    """Activate module-scoped RoleBinding, disable aggregation, wait for RBAC revocation."""
    role_name = request.param
    request.getfixturevalue(f"{role_name}_role_binding")
    wait_for_vm_list_access(client=unprivileged_client, namespace_name=namespace.name)
    yield from disable_aggregation_and_wait(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_module,
        role_name=role_name,
    )


@pytest.fixture()
def reenabled_aggregation_state(admin_client, hyperconverged_resource_scope_module):
    """Verify aggregation is AggregateToDefault, wait for labels to be present."""
    ensure_aggregation_enabled(
        admin_client=admin_client,
        hyperconverged_resource=hyperconverged_resource_scope_module,
    )


@pytest.fixture()
def vm_collection_resource_for_unprivileged_client(unprivileged_client):
    """VirtualMachine API resource handle for the unprivileged client."""
    return unprivileged_client.resources.get(api_version="kubevirt.io/v1", kind="VirtualMachine")


@pytest.fixture()
def dry_run_vm(unprivileged_client, namespace):
    """Minimal VirtualMachine configured for server-side dry-run creation."""
    return VirtualMachine(
        name="rbac-dry-run-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        body={
            "spec": {
                "running": False,
                "template": {
                    "spec": {
                        "domain": {
                            "devices": {},
                            "resources": {
                                "requests": {
                                    "memory": "64Mi",
                                },
                            },
                        },
                    },
                },
            },
        },
        dry_run=True,
    )
