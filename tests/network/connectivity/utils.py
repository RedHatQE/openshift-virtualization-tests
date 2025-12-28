import ipaddress
from collections import OrderedDict

from tests.network.libs.ip import random_ipv4_address, random_ipv6_address
from utilities.virt import VirtualMachineForTests, fedora_vm_body


def create_running_vm(
    name,
    node_selector,
    network_names,
    client,
    namespace,
    cloud_init_data,
):
    networks = OrderedDict()

    for network_name in network_names:
        networks[network_name] = network_name

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=node_selector,
        cloud_init_data=cloud_init_data,
        client=client,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


def secondary_interfaces_cloud_init_data(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    host_id: int,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    ethernets = {}
    for i in range(3):
        interface_name = f"eth{i + 1}"
        addresses = []
        if ipv4_supported_cluster:
            addresses.append(f"{random_ipv4_address(net_seed=i, host_address=host_id)}/24")
        if ipv6_supported_cluster:
            addresses.append(f"{random_ipv6_address(net_seed=i, host_address=host_id)}/64")

        ethernets[interface_name] = {"addresses": addresses}

    return {"ethernets": ethernets}


def filter_link_local_addresses(ip_addresses: list[str]) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ip for addr in ip_addresses if not (ip := ipaddress.ip_interface(address=addr).ip).is_link_local]
