from typing import Final

from kubernetes.dynamic import DynamicClient

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.vmspec import lookup_iface_status
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import (
    CloudInitNoCloud,
    Devices,
    Interface,
    Multus,
    Network,
)
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit

NET_SEED: Final[int] = 0


REF_VM_IFACE_A_HOST_ADDRESS: Final[int] = 1
REF_VM_IFACE_B_HOST_ADDRESS: Final[int] = 2
UNDER_TEST_VM_HOST_ADDRESS: Final[int] = 3
UNDER_TEST_VM_2ND_IFACE_HOST_ADDRESS: Final[int] = 4

UNDER_TEST_VM_IFACE_1: Final[str] = "iface-1"
UNDER_TEST_VM_IFACE_2: Final[str] = "iface-2"

REF_VM_NS_VLAN_A: Final[str] = "ns-vlan-a"
REF_VM_NS_VLAN_B: Final[str] = "ns-vlan-b"


def _primary_iface_cloud_init() -> cloudinit.EthernetDevice | None:
    """Return cloud-init config for the masquerade primary interface.

    Returns None on IPv4-only clusters (no eth0 config needed when IPv6 is absent).
    """
    if not ipv6_supported_cluster():
        return None
    return cloudinit.EthernetDevice(
        addresses=["fd10:0:2::2/120"],
        gateway6="fd10:0:2::1",
        dhcp4=ipv4_supported_cluster(),
        dhcp6=False,
    )


def bridge_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_names: list[str],
    ip_addresses: list[list[str]],
    iface_names: list[str] | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM with a masquerade primary interface and bridge-bound secondary interfaces.

    Interface layout in guest OS:
        eth0 = masquerade (pod network, primary — handles default route and IPv6)
        eth1 = first secondary bridge interface
        eth2 = second secondary bridge interface (if present)

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name.
        client: Kubernetes dynamic client.
        nad_names: NAD names (multus networkName) for the secondary interfaces, in spec order.
        ip_addresses: Per-interface CIDR address lists, aligned with nad_names.
            Each inner list contains one address per supported IP family.
        iface_names: Logical interface names for the VM spec. When omitted, nad_names are used.
            Required when multiple interfaces reference the same NAD to ensure unique names.
    """
    actual_iface_names = iface_names or nad_names
    spec = base_vmspec()
    spec.template.spec.domain.devices = Devices(
        interfaces=[
            Interface(name="default", masquerade={}),
            *[Interface(name=iface_name, bridge={}) for iface_name in actual_iface_names],
        ]
    )
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        *[
            Network(name=iface_name, multus=Multus(networkName=nad_name))
            for iface_name, nad_name in zip(actual_iface_names, nad_names)
        ],
    ]
    ethernets = {}
    primary = _primary_iface_cloud_init()
    if primary:
        ethernets["eth0"] = primary
    for i, addresses in enumerate(ip_addresses):
        if not addresses:
            # Suppress DHCP so cloud-init's network module does not time out waiting
            # for DHCP on interfaces that will be moved to namespaces via runcmd.
            ethernets[f"eth{i + 1}"] = cloudinit.EthernetDevice(dhcp4=False, dhcp6=False)
        else:
            ethernets[f"eth{i + 1}"] = cloudinit.EthernetDevice(addresses=addresses)
    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)) if ethernets else "",
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


def iface_info(vm: BaseVirtualMachine, iface_name: str) -> dict:
    iface = lookup_iface_status(vm=vm, iface_name=iface_name)
    return {
        "name": iface.name,
        "macAddress": iface.macAddress,
        "ipAddresses": list(iface.ipAddresses or []),
    }
