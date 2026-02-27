import logging
from collections.abc import Iterator

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.resource import ResourceField

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.ip import random_ipv4_address, random_ipv6_address

LOGGER = logging.getLogger(__name__)
LINUX_BRIDGE_IFACE_NAME = "linux-bridge"


def primary_iface_cloud_init(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> cloudinit.EthernetDevice | None:
    if not ipv6_supported_cluster:
        return None
    return cloudinit.EthernetDevice(
        addresses=["fd10:0:2::2/120"],
        gateway6="fd10:0:2::1",
        dhcp4=ipv4_supported_cluster,
        dhcp6=False,
    )


def secondary_iface_cloud_init(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> cloudinit.EthernetDevice:
    addresses = []
    if ipv4_supported_cluster:
        addresses.append(f"{random_ipv4_address(net_seed=0, host_address=1)}/24")
    if ipv6_supported_cluster:
        addresses.append(f"{random_ipv6_address(net_seed=0, host_address=1)}/64")
    return cloudinit.EthernetDevice(addresses=addresses)


def linux_bridge_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    bridge_network_name: str,
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> BaseVirtualMachine:
    spec = base_vmspec()
    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name="default", masquerade={}),
        Interface(name=LINUX_BRIDGE_IFACE_NAME, bridge={}),
    ]
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        Network(name=LINUX_BRIDGE_IFACE_NAME, multus=Multus(networkName=bridge_network_name)),
    ]

    ethernets = {}
    primary = primary_iface_cloud_init(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    )
    if primary:
        ethernets["eth0"] = primary

    ethernets["eth1"] = secondary_iface_cloud_init(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    )

    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)),
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)

    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


def monitor_vmi_events(vm: BaseVirtualMachine, watcher_timeout: int, context: str = "") -> Iterator[ResourceField]:
    vmi = vm.vmi
    context_msg = f" {context}" if context else ""

    LOGGER.info(
        f"Starting {watcher_timeout} seconds monitoring of ipAddress field stability on VMI {vmi.name}{context_msg}"
    )

    for event in vmi.watcher(timeout=watcher_timeout):
        if event["type"] != "MODIFIED":
            continue

        event_vmi = event["object"]
        LOGGER.info(f"Event: VMI {vmi.name} status updated{context_msg}")
        yield event_vmi
