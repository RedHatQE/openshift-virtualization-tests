"""SR-IOV library constants and utilities."""

from kubernetes.dynamic import DynamicClient

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.ip import random_ipv4_address, random_ipv6_address
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Memory, Multus, Network
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.cloudinit import MatchSelector
from utilities.constants.networking import SRIOV
from utilities.infra import get_node_selector_dict
from utilities.network import compose_cloud_init_data_dict, sriov_network_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body

VM_SRIOV_IFACE_NAME = "sriov1"
MTU_9000 = 9000


def base_sriov_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    sriov_network_name: str,
    sriov_mac: str,
    addresses: list[str],
    memory_guest: str = "1Gi",
    memory_max_guest: str | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM with an SR-IOV secondary interface using BaseVirtualMachine.

    The SR-IOV VF is matched by MAC address and renamed to sriov1 via
    cloud-init set-name.

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name prefix (a unique suffix is appended automatically).
        client: Kubernetes dynamic client.
        sriov_network_name: Name of the SR-IOV NetworkAttachmentDefinition.
        sriov_mac: MAC address to assign to the SR-IOV interface.
        addresses: CIDR addresses to assign to the SR-IOV interface
            (e.g. ["172.16.0.1/24", "fd00::1/64"]).
        memory_guest: Initial guest memory (e.g. "1Gi"). Defaults to "1Gi".
        memory_max_guest: Maximum guest memory for hot-plug. None disables hot-plug.

    Returns:
        BaseVirtualMachine configured with an SR-IOV secondary interface.
    """
    spec = base_vmspec()
    spec.template.spec.domain.memory = Memory(guest=memory_guest, maxGuest=memory_max_guest)
    spec.template.spec.domain.devices.interfaces = [  # type: ignore[union-attr]
        Interface(name=sriov_network_name, sriov={}, macAddress=sriov_mac),
    ]
    spec.template.spec.networks = [
        Network(name=sriov_network_name, multus=Multus(networkName=f"{namespace}/{sriov_network_name}")),
    ]

    ethernets: dict[str, cloudinit.EthernetDevice] = {}
    ethernets["sriov"] = cloudinit.EthernetDevice(
        addresses=addresses,
        match=MatchSelector(macaddress=sriov_mac),
        set_name=VM_SRIOV_IFACE_NAME,
    )
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)),
            userData=cloudinit.format_cloud_config(userdata=cloudinit.UserData(users=[])),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


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
    ipv6_primary_interface_cloud_init_data=None,
):
    sriov_addresses = []
    if ipv4_supported_cluster():
        sriov_addresses.append(random_ipv4_address(net_seed=net_seed, host_address=host_address))
    if ipv6_supported_cluster():
        sriov_addresses.append(random_ipv6_address(net_seed=net_seed, host_address=host_address))

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
