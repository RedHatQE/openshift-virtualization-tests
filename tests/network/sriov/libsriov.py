from tests.network.libs.ip import random_ipv4_address, random_ipv6_address
from utilities.constants import SRIOV
from utilities.infra import get_node_selector_dict
from utilities.network import compose_cloud_init_data_dict, sriov_network_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body

VM_SRIOV_IFACE_NAME = "sriov1"


def vm_sriov_mac(mac_suffix_index):
    return f"02:00:b5:b5:b5:{mac_suffix_index:02x}"


def sriov_vm(
    unprivileged_client,
    name,
    namespace,
    sriov_network,
    cloud_init_data,
    worker=None,
):
    sriov_mac = cloud_init_data["networkData"]["ethernets"]["1"]["match"]["macaddress"]
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)

    vm_kwargs = {
        "namespace": namespace.name,
        "name": name,
        "body": fedora_vm_body(name=name),
        "networks": networks,
        "interfaces": networks.keys(),
        "cloud_init_data": cloud_init_data,
        "client": unprivileged_client,
        "macs": {sriov_network.name: sriov_mac},
        "interfaces_types": {name: SRIOV for name in networks.keys()},
    }

    if worker:
        vm_kwargs["node_selector"] = get_node_selector_dict(node_selector=worker.name)
    with VirtualMachineForTests(**vm_kwargs) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


def sriov_cloud_init_data(
    sriov_mac,
    net_seed,
    host_address,
    ipv4_supported_cluster,
    ipv6_supported_cluster,
    ipv6_primary_interface_cloud_init_data=None,
):
    sriov_addresses = []
    if ipv4_supported_cluster:
        sriov_addresses.append(f"{random_ipv4_address(net_seed=net_seed, host_address=host_address)}/24")
    if ipv6_supported_cluster:
        sriov_addresses.append(f"{random_ipv6_address(net_seed=net_seed, host_address=host_address)}/64")

    sriov_interface_data = {
        "ethernets": {
            "1": {
                "addresses": sriov_addresses,
                "match": {"macaddress": sriov_mac},
                "set-name": VM_SRIOV_IFACE_NAME,
            }
        }
    }
    return compose_cloud_init_data_dict(
        network_data=sriov_interface_data,
        ipv6_network_data=ipv6_primary_interface_cloud_init_data,
    )
