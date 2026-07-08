from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from ocp_resources.virtual_machine import VirtualMachine

from tests.install_upgrade_operators.role_aggregation.utils import (
    disabled_aggregation_with_role_binding,
    reenabled_aggregation_with_role_binding,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from kubernetes.dynamic.resource import Resource
    from ocp_resources.hyperconverged import HyperConverged
    from ocp_resources.namespace import Namespace


@pytest.fixture()
def disabled_aggregation_with_role(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    hyperconverged_resource_scope_class: HyperConverged,
) -> Generator[None]:
    """RoleBinding → baseline access verified → Manual → labels removed → RBAC revoked."""
    yield from disabled_aggregation_with_role_binding(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name=request.param,
    )


@pytest.fixture()
def vm_resource_for_unprivileged_client(unprivileged_client: DynamicClient) -> Resource:
    """VirtualMachine API resource handle for the unprivileged client."""
    return unprivileged_client.resources.get(api_version="kubevirt.io/v1", kind="VirtualMachine")


@pytest.fixture()
def dry_run_vm(unprivileged_client: DynamicClient, namespace: Namespace) -> VirtualMachine:
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
def admin_reenabled_aggregation(
    admin_client: DynamicClient, namespace: Namespace, hyperconverged_resource_scope_class: HyperConverged
) -> Generator[None]:
    """Manual → admin RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="admin",
    )


@pytest.fixture()
def edit_reenabled_aggregation(
    admin_client: DynamicClient, namespace: Namespace, hyperconverged_resource_scope_class: HyperConverged
) -> Generator[None]:
    """Manual → edit RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="edit",
    )


@pytest.fixture()
def view_reenabled_aggregation(
    admin_client: DynamicClient, namespace: Namespace, hyperconverged_resource_scope_class: HyperConverged
) -> Generator[None]:
    """Manual → view RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="view",
    )
