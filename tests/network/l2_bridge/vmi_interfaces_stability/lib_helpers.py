import ipaddress
import logging
from collections.abc import Iterator
from typing import Final

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.resource import ResourceField
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from libs.net.ip import random_ipv4_address, random_ipv6_address
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.guest import guest_iface_name
from libs.vm.spec import CloudInitNoCloud, Interface, Multus, Network
from libs.vm.vm import (
    BaseVirtualMachine,
    add_volume_disk,
    cloudinitdisk_storage,
)
from tests.network.libs import cloudinit

LOGGER = logging.getLogger(__name__)

LINUX_BRIDGE_IFACE_NAME_1: Final[str] = "linux-bridge-1"
LINUX_BRIDGE_IFACE_NAME_2: Final[str] = "linux-bridge-2"


def secondary_network_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    bridge_network_name: str,
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> BaseVirtualMachine:
    spec = base_vmspec()
    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name=LINUX_BRIDGE_IFACE_NAME_1, bridge={}),
        Interface(name="default", masquerade={}),
        Interface(name=LINUX_BRIDGE_IFACE_NAME_2, bridge={}),
    ]
    spec.template.spec.networks = [
        Network(name=LINUX_BRIDGE_IFACE_NAME_1, multus=Multus(networkName=bridge_network_name)),
        Network(name="default", pod={}),
        Network(name=LINUX_BRIDGE_IFACE_NAME_2, multus=Multus(networkName=bridge_network_name)),
    ]

    ethernets = {}
    primary = primary_iface_cloud_init(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    )
    if primary:
        ethernets[guest_iface_name(ordinal=2)] = primary

    ethernets[guest_iface_name(ordinal=1)] = secondary_iface_cloud_init(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
        host_address=1,
    )

    ethernets[guest_iface_name(ordinal=3)] = secondary_iface_cloud_init(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
        host_address=2,
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
    host_address: int,
) -> cloudinit.EthernetDevice:
    ips = secondary_iface_ips(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
        host_address=host_address,
    )
    addresses = [f"{ip}/64" if ipaddress.ip_address(ip).version == 6 else f"{ip}/24" for ip in ips]
    return cloudinit.EthernetDevice(addresses=addresses)


def secondary_iface_ips(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    host_address: int,
) -> list[str]:
    ips = []
    if ipv4_supported_cluster:
        ips.append(random_ipv4_address(net_seed=0, host_address=host_address))
    if ipv6_supported_cluster:
        ips.append(random_ipv6_address(net_seed=0, host_address=host_address))
    return ips


def wait_for_stable_ifaces(
    vm: BaseVirtualMachine,
) -> None:
    primary_network = lookup_primary_network(vm=vm)

    ethernets = vm.cloud_init_network_data.ethernets
    secondary_iface_to_ips = {
        LINUX_BRIDGE_IFACE_NAME_1: [
            str(ipaddress.ip_interface(addr).ip)
            for addr in ethernets[guest_iface_name(ordinal=1)].addresses  # type: ignore[union-attr]
        ],
        LINUX_BRIDGE_IFACE_NAME_2: [
            str(ipaddress.ip_interface(addr).ip)
            for addr in ethernets[guest_iface_name(ordinal=3)].addresses  # type: ignore[union-attr]
        ],
    }

    spec_interfaces = vm.instance.spec.template.spec.domain.devices.interfaces
    for iface in spec_interfaces:
        if iface.name == primary_network.name:
            lookup_iface_status(vm=vm, iface_name=iface.name)
        else:
            lookup_iface_status(
                vm=vm,
                iface_name=iface.name,
                predicate=lambda iface_status: (
                    "guest-agent" in iface_status["infoSource"]
                    and all(ip in iface_status.get("ipAddresses", []) for ip in secondary_iface_to_ips[iface.name])
                ),
            )


def assert_interfaces_stable(stable_ips: dict[str, str], vmi: VirtualMachineInstance, expected_num_ifaces: int) -> None:
    interfaces = vmi.status.interfaces
    assert interfaces, "VMI has no interfaces"
    assert len(interfaces) == expected_num_ifaces, f"Expected {expected_num_ifaces} interfaces, got {len(interfaces)}"
    for iface in interfaces:
        assert iface.ipAddress, f"ipAddress missing on interface {iface.name}"
        assert iface.ipAddress == stable_ips[iface.name], (
            f"IP mismatch on {iface.name}: event reports {iface.ipAddress}, stable state has {stable_ips[iface.name]}"
        )


def monitor_vmi_events(vm: BaseVirtualMachine, timeout: int) -> Iterator[ResourceField]:
    vmi = vm.vmi

    LOGGER.info(f"Starting {timeout} seconds monitoring of interfaces stability on VMI {vmi.name}")

    for event in vmi.watcher(timeout=timeout):
        if event["type"] != "MODIFIED":
            continue

        vmi_obj = event["object"]
        LOGGER.info(f"Event: VMI {vmi.name} status updated")
        yield vmi_obj
