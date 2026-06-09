import ipaddress
from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.traffic_generator import TcpServer, client_server_active_connection
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME
from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm


@pytest.fixture(scope="module")
def vm_under_test(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="ip-spec-vm-under-test",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        template_labels=dict((udn_affinity_label,)),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_for_connectivity_ref(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vm-for-connectivity-ref",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        template_labels=dict((udn_affinity_label,)),
    ) as vm:
        vm.start()
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def ip_to_request(
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    vm_for_connectivity_ref: BaseVirtualMachine,
) -> ipaddress.IPv4Interface | ipaddress.IPv6Interface:
    used_ip = lookup_iface_status_ip(
        vm=vm_for_connectivity_ref,
        iface_name=lookup_primary_network(vm=vm_for_connectivity_ref).name,
        ip_family=4,
    )

    (subnet,) = namespaced_layer2_user_defined_network.subnets
    ip_net = ipaddress.ip_network(address=subnet)

    # The first two addresses are reserved by the network provider (OVN-K).
    # Therefore, skip the first two.
    network_hosts = (ip for ip in ip_net.hosts() if ip != used_ip)
    for _ in range(2):
        next(network_hosts)
    new_ip = next(network_hosts)

    return ipaddress.ip_interface(address=(new_ip, ip_net.prefixlen))


@pytest.fixture(scope="module")
def client_server_tcp_connectivity_between_vms(
    vm_for_connectivity_ref: BaseVirtualMachine, vm_under_test: BaseVirtualMachine
) -> Generator[tuple[TcpClient, TcpServer]]:
    with client_server_active_connection(
        client_vm=vm_for_connectivity_ref,
        server_vm=vm_under_test,
        spec_logical_network=lookup_primary_network(vm=vm_under_test).name,
    ) as (client, server):
        yield client, server
