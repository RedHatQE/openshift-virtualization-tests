import pytest
from ocp_resources.virtual_machine import VirtualMachine

from tests.install_upgrade_operators.role_aggregation.utils import (
    disabled_aggregation_with_role_binding,
    reenabled_aggregation_with_role_binding,
)


@pytest.fixture()
def disabled_aggregation_with_role(
    request,
    admin_client,
    unprivileged_client,
    namespace,
    hyperconverged_resource_scope_class,
):
    """RoleBinding → baseline access verified → Manual → labels removed → RBAC revoked."""
    yield from disabled_aggregation_with_role_binding(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name=request.param,
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


@pytest.fixture()
def reenabled_aggregation_with_role(request, admin_client, namespace, hyperconverged_resource_scope_class):
    """Manual → RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name=request.param,
    )
