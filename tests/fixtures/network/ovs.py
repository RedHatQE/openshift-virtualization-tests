import logging

import pytest

from utilities.infra import get_pods, wait_for_pods_deletion
from utilities.network import (
    enable_hyperconverged_ovs_annotations,
    wait_for_ovs_daemonset_resource,
    wait_for_ovs_status,
)
from utilities.virt import get_hyperconverged_ovs_annotations

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def ovs_daemonset(admin_client, hco_namespace):
    return wait_for_ovs_daemonset_resource(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hyperconverged_ovs_annotations_fetched(hyperconverged_resource_scope_function):
    return get_hyperconverged_ovs_annotations(hyperconverged=hyperconverged_resource_scope_function)


@pytest.fixture(scope="session")
def hyperconverged_ovs_annotations_enabled_scope_session(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_session,
    network_addons_config_scope_session,
):
    yield from enable_hyperconverged_ovs_annotations(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_session,
        network_addons_config=network_addons_config_scope_session,
    )

    wait_for_ovs_status(network_addons_config=network_addons_config_scope_session, status=False)
    wait_for_pods_deletion(
        pods=get_pods(
            client=admin_client,
            namespace=hco_namespace,
            label="app=ovs-cni",
        )
    )
