from copy import deepcopy
from typing import Final

from kubernetes.dynamic import DynamicClient

from libs.net.vmspec import wait_for_no_vmi_condition, wait_for_vmi_condition_status
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
from tests.network.libs.cloudinit import primary_iface_cloud_init
from tests.network.libs.connectivity import poll_tcp_connectivity

NET_SEED: Final[int] = 0


GUEST_IFACE_1: Final[str] = "eth1"
GUEST_IFACE_2: Final[str] = "eth2"


def assert_connectivity(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    server_ip: str,
    server_bind_dev: str,
    client_bind_dev: str,
) -> None:
    """Assert TCP connectivity from client to server for a single IP address.

    Args:
        client_vm: VM initiating the connection.
        server_vm: VM accepting the connection.
        server_ip: IP address to connect to.
        server_bind_dev: Guest device to bind the iperf3 server to (bypasses ECMP).
        client_bind_dev: Guest device to bind the iperf3 client to (bypasses ECMP).
    """
    poll_tcp_connectivity(
        client_vm=client_vm,
        server_vm=server_vm,
        server_ip=server_ip,
        client_bind_dev=client_bind_dev,
        server_bind_dev=server_bind_dev,
    )


def assert_no_connectivity(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    server_ip: str,
    server_bind_dev: str,
    client_bind_dev: str,
) -> None:
    """Assert no TCP connectivity from client to server for a single IP address.

    Args:
        client_vm: VM initiating the connection.
        server_vm: VM accepting the connection.
        server_ip: IP address to connect to.
        server_bind_dev: Guest device to bind the iperf3 server to (bypasses ECMP).
        client_bind_dev: Guest device to bind the iperf3 client to (bypasses ECMP).
    """
    poll_tcp_connectivity(
        client_vm=client_vm,
        server_vm=server_vm,
        server_ip=server_ip,
        client_bind_dev=client_bind_dev,
        server_bind_dev=server_bind_dev,
        expect_connectivity=False,
    )


def update_nad_references(vm: BaseVirtualMachine, nad_name_by_net: dict[str, str]) -> None:
    """Update secondary network NAD references and wait for the change to be fully applied.

    Patches the VM spec atomically, then waits for the MigrationRequired condition to
    appear (change detected) and disappear (migration completed).

    Args:
        vm: The virtual machine to update.
        nad_name_by_net: Mapping of interface name to new NAD name.
    """
    resource_version = vm.vmi.instance.metadata.resourceVersion
    networks = deepcopy(vm.template_spec.networks) or []
    for network in networks:
        if network.name in nad_name_by_net and network.multus:
            network.multus.networkName = nad_name_by_net[network.name]
    vm.set_networks(networks=networks)
    wait_for_vmi_condition_status(vm=vm, condition="MigrationRequired", resource_version=resource_version)
    wait_for_no_vmi_condition(vm=vm, condition="MigrationRequired")


def two_secondary_bridge_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_names: list[str],
    ip_addresses: list[list[str]],
    iface_names: list[str],
    runcmd: list[str] | None = None,
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
        iface_names: Logical interface names for the VM spec, aligned with nad_names.
        runcmd: Commands to run on first boot via cloud-init runcmd. None means no extra commands.
    """
    spec = base_vmspec()
    spec.template.spec.domain.devices = Devices(
        interfaces=[
            Interface(name="default", masquerade={}),
            *[Interface(name=iface_name, bridge={}) for iface_name in iface_names],
        ]
    )
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        *[
            Network(name=iface_name, multus=Multus(networkName=nad_name))
            for iface_name, nad_name in zip(iface_names, nad_names)
        ],
    ]
    ethernets = {}
    if primary := primary_iface_cloud_init():
        ethernets["eth0"] = primary
    for i, addresses in enumerate(ip_addresses):
        ethernets[f"eth{i + 1}"] = cloudinit.EthernetDevice(addresses=addresses)
    userdata = cloudinit.UserData(users=[], runcmd=runcmd)
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)) if ethernets else "",
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)
