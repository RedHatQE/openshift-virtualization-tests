import pytest

NODE_MAINTENANCE_OPERATOR = "node-maintenance-operator"

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture()
def node_maintenance_resources(admin_client, hco_namespace, nmo_removal_matrix__function__):
    return [
        resource.name
        for resource in nmo_removal_matrix__function__.get(dyn_client=admin_client, namespace=hco_namespace.name)
        if resource.name.startswith(NODE_MAINTENANCE_OPERATOR)
    ]


@pytest.mark.polarion("CNV-8742")
def test_validate_nmo_removal(hco_namespace, nmo_removal_matrix__function__, node_maintenance_resources):
    assert not node_maintenance_resources, (
        f"Following {NODE_MAINTENANCE_OPERATOR} resource: {nmo_removal_matrix__function__} has been found in namespace"
        f" {hco_namespace.name}: {node_maintenance_resources}"
    )
