import pytest

from tests.network.network_policy.libnetpolicy import ApplyNetworkPolicy
from utilities.constants import PORT_80
from utilities.infra import create_ns, get_node_selector_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body

PORT_81 = 81


@pytest.fixture(scope="module")
def namespace_1(admin_client, unprivileged_client):
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="network-policy-test-1",
    )


@pytest.fixture(scope="module")
def namespace_2(admin_client, unprivileged_client):
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="network-policy-test-2",
    )


@pytest.fixture()
def deny_all_http_ports(unprivileged_client, namespace_1):
    with ApplyNetworkPolicy(name="deny-all-http-ports", namespace=namespace_1.name, client=unprivileged_client) as np:
        yield np


@pytest.fixture()
def allow_all_http_ports(unprivileged_client, namespace_1):
    with ApplyNetworkPolicy(
        name="allow-all-http-ports",
        namespace=namespace_1.name,
        ports=[PORT_80, PORT_81],
        client=unprivileged_client,
    ) as np:
        yield np


@pytest.fixture()
def allow_http80_port(unprivileged_client, namespace_1):
    with ApplyNetworkPolicy(
        name="allow-http80-port",
        namespace=namespace_1.name,
        ports=[PORT_80],
        client=unprivileged_client,
    ) as np:
        yield np


@pytest.fixture(scope="module")
def network_policy_vma(unprivileged_client, worker_node1, namespace_1):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace_1.name,
        name=name,
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def network_policy_vmb(unprivileged_client, worker_node1, namespace_2):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace_2.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_network_policy_vma(network_policy_vma):
    network_policy_vma.wait_for_agent_connected()
    return network_policy_vma


@pytest.fixture(scope="module")
def running_network_policy_vmb(network_policy_vmb):
    network_policy_vmb.wait_for_agent_connected()
    return network_policy_vmb