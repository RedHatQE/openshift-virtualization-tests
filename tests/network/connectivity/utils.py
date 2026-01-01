from collections import OrderedDict

from tests.network.libs.ip import random_ipv4_address, random_ipv6_address
from utilities.network import (
    compose_cloud_init_data_dict,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body


def create_running_vm(
    ipv4_supported_cluster,
    ipv6_supported_cluster,
    namespace,
    client,
    node_selector,
    network_names,
    ipv6_primary_interface_cloud_init_data,
    name,
    host_id,
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
        cloud_init_data=compose_cloud_init_data_dict(
            ipv6_network_data=ipv6_primary_interface_cloud_init_data,
            network_data=secondary_interfaces_cloud_init_data(
                ipv4_supported_cluster=ipv4_supported_cluster,
                ipv6_supported_cluster=ipv6_supported_cluster,
                host_id=host_id,
            ),
        ),
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
    return {
        "ethernets": {
            f"eth{i + 1}": {
                "addresses": (
                    [f"{random_ipv4_address(net_seed=i, host_address=host_id)}/24"] if ipv4_supported_cluster else []
                )
                + ([f"{random_ipv6_address(net_seed=i, host_address=host_id)}/64"] if ipv6_supported_cluster else [])
            }
            for i in range(0, 3)
        }
    }
