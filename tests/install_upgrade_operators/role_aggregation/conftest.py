import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.virtual_machine import VirtualMachine

from tests.install_upgrade_operators.role_aggregation.utils import (
    unprivileged_role_binding,
    wait_for_aggregation_labels,
)
from utilities.hco import ResourceEditorValidateHCOReconcile


@pytest.fixture(scope="class")
def admin_role_binding(admin_client, namespace):
    """RoleBinding granting admin ClusterRole to the unprivileged user."""
    yield from unprivileged_role_binding(admin_client=admin_client, namespace_name=namespace.name, role_name="admin")


@pytest.fixture(scope="class")
def edit_role_binding(admin_client, namespace):
    """RoleBinding granting edit ClusterRole to the unprivileged user."""
    yield from unprivileged_role_binding(admin_client=admin_client, namespace_name=namespace.name, role_name="edit")


@pytest.fixture(scope="class")
def view_role_binding(admin_client, namespace):
    """RoleBinding granting view ClusterRole to the unprivileged user."""
    yield from unprivileged_role_binding(admin_client=admin_client, namespace_name=namespace.name, role_name="view")


@pytest.fixture(scope="function")
def aggregation_disabled(admin_client, hyperconverged_resource_scope_class):
    """HCO with roleAggregationStrategy set to Manual and aggregation labels removed."""
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_class: {"spec": {"roleAggregationStrategy": "Manual"}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
    ):
        wait_for_aggregation_labels(admin_client=admin_client, should_be_present=False)
        yield


@pytest.fixture(scope="function")
def aggregation_reenabled(admin_client, hyperconverged_resource_scope_class):
    """HCO with roleAggregationStrategy at AggregateToDefault and aggregation labels present."""
    current_strategy = hyperconverged_resource_scope_class.instance.spec.get(
        "roleAggregationStrategy", "AggregateToDefault"
    )
    assert current_strategy == "AggregateToDefault", (
        f"roleAggregationStrategy is {current_strategy}, expected AggregateToDefault"
    )
    wait_for_aggregation_labels(admin_client=admin_client, should_be_present=True)


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
