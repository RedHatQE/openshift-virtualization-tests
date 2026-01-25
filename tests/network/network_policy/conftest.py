import pytest

from tests.network.network_policy.libnetpolicy import TEST_PORTS, ApplyNetworkPolicy
from utilities.infra import create_ns, get_node_selector_dict
from utilities.network import compose_cloud_init_data_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body, prepare_cloud_init_user_data


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
        ports=TEST_PORTS,
        client=unprivileged_client,
    ) as np:
        yield np


@pytest.fixture()
def allow_single_http_port(unprivileged_client, namespace_1):
    with ApplyNetworkPolicy(
        name="allow-single-http-port",
        namespace=namespace_1.name,
        ports=[TEST_PORTS[0]],
        client=unprivileged_client,
    ) as np:
        yield np


@pytest.fixture(scope="module")
def network_policy_vma(
    unprivileged_client,
    worker_node1,
    namespace_1,
    ipv6_primary_interface_cloud_init_data,
):
    name = "vma-network-policy"
    http_server_commands = [f"python3 -m http.server {port} --bind :: &" for port in TEST_PORTS]

    cloud_init_data = compose_cloud_init_data_dict(ipv6_network_data=ipv6_primary_interface_cloud_init_data)
    cloud_init_data.update(prepare_cloud_init_user_data(section="runcmd", data=http_server_commands))

    with VirtualMachineForTests(
        namespace=namespace_1.name,
        name=name,
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def network_policy_vmb(unprivileged_client, worker_node1, namespace_2, ipv6_primary_interface_cloud_init_data):
    name = "vmb-network-policy"
    cloud_init_data = compose_cloud_init_data_dict(ipv6_network_data=ipv6_primary_interface_cloud_init_data)
    with VirtualMachineForTests(
        namespace=namespace_2.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
