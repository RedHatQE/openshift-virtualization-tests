from typing import Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import (
    CloudInitNoCloud,
    Devices,
    Interface,
    Multus,
    Network,
    VMSpec,
)
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage, data_volume_storage
from tests.network.l2_bridge.libl2bridge import LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2
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


def assert_baseline_connectivity(
    client_vm: BaseVirtualMachine,
    ref_vm: BaseVirtualMachine,
) -> None:
    """Assert baseline connectivity: client reaches ref on VLAN-A, not on VLAN-B.

    Args:
        client_vm: VM initiating the connections.
        ref_vm: Reference VM with interfaces on both VLANs.
    """
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=LINUX_BRIDGE_IFACE_NAME_1).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=ref_vm,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_IFACE_1,
        )
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=LINUX_BRIDGE_IFACE_NAME_2).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=ref_vm,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_IFACE_2,
            expect_connectivity=False,
        )


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
    return fedora_vm(
        namespace=namespace,
        name=name,
        client=client,
        spec=_bridge_vm_spec(
            nad_names=nad_names,
            ip_addresses=ip_addresses,
            iface_names=iface_names,
            runcmd=runcmd,
        ),
    )


def non_migratable_bridge_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_names: list[str],
    ip_addresses: list[list[str]],
    iface_names: list[str],
    data_volume: DataVolume,
    runcmd: list[str] | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM with secondary bridge interfaces backed by an existing RWO DataVolume.

    The VM references the provided, already-deployed DataVolume by name via a dataVolume
    volume reference. The RWO access mode of the backing PVC makes the VM non-live-migratable.

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name.
        client: Kubernetes dynamic client.
        nad_names: NAD names for the secondary interfaces, in spec order.
        ip_addresses: Per-interface CIDR address lists, aligned with nad_names.
        iface_names: Logical interface names for the VM spec, aligned with nad_names.
        data_volume: Existing deployed DataVolume referenced by name; its RWO access mode
            makes the VM non-migratable.
        runcmd: Commands to run on first boot via cloud-init runcmd. None means no extra commands.
    """
    spec = _bridge_vm_spec(
        nad_names=nad_names,
        ip_addresses=ip_addresses,
        iface_names=iface_names,
        runcmd=runcmd,
    )
    disk, volume = data_volume_storage(name=data_volume.name)
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


def _bridge_vm_spec(
    nad_names: list[str],
    ip_addresses: list[list[str]],
    iface_names: list[str],
    runcmd: list[str] | None = None,
) -> VMSpec:
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
    return spec
