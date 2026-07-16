import logging

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.sriov_network_node_policy import SriovNetworkNodePolicy

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sriov_namespace(admin_client):
    return Namespace(name="openshift-sriov-network-operator", client=admin_client)


@pytest.fixture(scope="session")
def sriov_workers(schedulable_nodes):
    sriov_worker_label = "feature.node.kubernetes.io/network-sriov.capable"
    yield [node for node in schedulable_nodes if node.labels.get(sriov_worker_label) == "true"]


@pytest.fixture(scope="session")
def sriov_node_policy(
    admin_client,
    sriov_namespace,
):
    if sriov_namespace.exists:
        return next(
            SriovNetworkNodePolicy.get(
                client=admin_client,
                namespace=sriov_namespace.name,
            ),
            None,
        )
    return None
