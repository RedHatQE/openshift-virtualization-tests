from __future__ import annotations

import pytest

from tests.install_upgrade_operators.role_aggregation.utils import reenabled_aggregation_with_role_binding


@pytest.fixture()
def admin_reenabled_aggregation(admin_client, namespace, hyperconverged_resource_scope_class):
    """Manual → admin RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="admin",
    )


@pytest.fixture()
def edit_reenabled_aggregation(admin_client, namespace, hyperconverged_resource_scope_class):
    """Manual → edit RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="edit",
    )


@pytest.fixture()
def view_reenabled_aggregation(admin_client, namespace, hyperconverged_resource_scope_class):
    """Manual → view RoleBinding → AggregateToDefault, with labels confirmed restored."""
    yield from reenabled_aggregation_with_role_binding(
        admin_client=admin_client,
        namespace_name=namespace.name,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        role_name="view",
    )
