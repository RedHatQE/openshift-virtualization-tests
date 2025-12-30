import pytest
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.vm import affinity
from tests.network.libs.ip import random_ipv4_address
from utilities.infra import create_ns


@pytest.fixture(scope="module")
def udn_namespace(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name="test-user-defined-network-ns",
        labels={"k8s.ovn.org/primary-user-defined-network": ""},
    )


@pytest.fixture(scope="module")
def namespaced_layer2_user_defined_network(admin_client, udn_namespace):
    with Layer2UserDefinedNetwork(
        name="layer2-udn",
        namespace=udn_namespace.name,
        role="Primary",
        subnets=[f"{random_ipv4_address(net_seed=0, host_address=0)}/24"],
        ipam={"lifecycle": "Persistent"},
        client=admin_client,
    ) as udn:
        udn.wait_for_condition(
            condition="NetworkAllocationSucceeded",
            status=udn.Condition.Status.TRUE,
        )
        yield udn


@pytest.fixture(scope="module")
def udn_affinity_label():
    return affinity.new_label(key_prefix="udn")
