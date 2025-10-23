import contextlib
from typing import Generator

from libs.net.traffic_generator import Client, Server
from libs.net.vmspec import IP_ADDRESS, add_network_interface, add_volume_disk, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.label_selector import LabelSelector

LOCALNET_BR_EX_NETWORK = "localnet-br-ex-network"
LOCALNET_OVS_BRIDGE_NETWORK = "localnet-ovs-network"
LOCALNET_TEST_LABEL = {"test": "localnet"}
LINK_STATE_UP = "up"
LINK_STATE_DOWN = "down"
_IPERF_SERVER_PORT = 5201


def run_vms(vms: tuple[BaseVirtualMachine, ...]) -> tuple[BaseVirtualMachine, ...]:
    for vm in vms:
        vm.start()  # type: ignore[no-untyped-call]
    for vm in vms:
        vm.wait_for_ready_status(status=True)  # type: ignore[no-untyped-call]
        vm.wait_for_agent_connected()
    return vms


def create_traffic_server(vm: BaseVirtualMachine) -> Server:
    return Server(vm=vm, port=_IPERF_SERVER_PORT)


def create_traffic_client(
    server_vm: BaseVirtualMachine, client_vm: BaseVirtualMachine, spec_logical_network: str
) -> Client:
    return Client(
        vm=client_vm,
        server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
        server_port=_IPERF_SERVER_PORT,
    )


def localnet_vm(
    namespace: str,
    name: str,
    physical_network_name: str,
    spec_logical_network: str,
    cidr: str,
    interface_state: str | None = None,
) -> BaseVirtualMachine:
    """
    Create a Fedora-based Virtual Machine connected to a given localnet network with a static IP configuration.

    The VM will:
    - Attach to a Multus network using a bridge interface.
    - Apply a specific label for anti-affinity scheduling.
    - Use cloud-init to configure a static IP address.
    - Based on a standard Fedora VM template.

    Args:
        namespace (str): The namespace where the VM should be created.
        name (str): The name of the VM.
        physical_network_name (str): The name of the Multus network to attach.
        cidr (str): The CIDR address to assign to the VM's interface.
        spec_logical_network (str): The name of the localnet network to attach.
        interface_state (str): The state of the interface (optional).
            Possible values are "up" or "down". When not specified, it behaves as "up".

    Returns:
        BaseVirtualMachine: The configured VM object ready for creation.
    """
    spec = base_vmspec()
    spec.template.metadata = spec.template.metadata or Metadata()
    spec.template.metadata.labels = spec.template.metadata.labels or {}
    spec.template.metadata.labels.update(LOCALNET_TEST_LABEL)
    vmi_spec = spec.template.spec

    vmi_spec = add_network_interface(
        vmi_spec=vmi_spec,
        network=Network(name=spec_logical_network, multus=Multus(networkName=physical_network_name)),
        interface=Interface(name=spec_logical_network, bridge={}, state=interface_state),
    )

    netdata = cloudinit.NetworkData(ethernets={"eth0": cloudinit.EthernetDevice(addresses=[cidr])})
    # Prevents cloud-init from overriding the default OS user credentials
    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=netdata), userData=cloudinit.format_cloud_config(userdata=userdata)
        )
    )
    vmi_spec = add_volume_disk(vmi_spec=vmi_spec, volume=volume, disk=disk)

    vmi_spec.affinity = new_pod_anti_affinity(label=next(iter(LOCALNET_TEST_LABEL.items())))
    vmi_spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].namespaceSelector = {}

    return fedora_vm(namespace=namespace, name=name, spec=spec)


def localnet_cudn(
    name: str,
    match_labels: dict[str, str],
    physical_network_name: str,
    vlan_id: int | None = None,
) -> libcudn.ClusterUserDefinedNetwork:
    """
    Create a ClusterUserDefinedNetwork resource configured for localnet with the specified VLAN ID.

    The function creates a CUDN with:
    - IPAM disabled
    - VLAN access mode with the specified VLAN ID
    - Localnet configuration with secondary role
    - Network topology set to LOCALNET

    Args:
        name (str): The name of the CUDN resource.
        match_labels (dict[str, str]): Labels for namespace selection.
        physical_network_name (str): The name of the physical network to associate with the localnet configuration.
        vlan_id (int|None): The VLAN ID to configure for the network. If None, no VLAN is configured.

    Returns:
        ClusterUserDefinedNetwork: The configured CUDN object ready for creation.
    """
    ipam = libcudn.Ipam(mode=libcudn.Ipam.Mode.DISABLED.value)
    vlan = libcudn.Vlan(mode=libcudn.Vlan.Mode.ACCESS.value, access=libcudn.Access(id=vlan_id)) if vlan_id else None
    localnet = libcudn.Localnet(
        role=libcudn.Localnet.Role.SECONDARY.value, physicalNetworkName=physical_network_name, vlan=vlan, ipam=ipam
    )
    network = libcudn.Network(topology=libcudn.Network.Topology.LOCALNET.value, localnet=localnet)

    return libcudn.ClusterUserDefinedNetwork(
        name=name, namespace_selector=LabelSelector(matchLabels=match_labels), network=network
    )


@contextlib.contextmanager
def client_server_active_connection(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    spec_logical_network: str,
    port: int = _IPERF_SERVER_PORT,
) -> Generator[tuple[Client, Server], None, None]:
    with Server(vm=server_vm, port=port) as server:
        with Client(
            vm=client_vm,
            server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
            server_port=port,
        ) as client:
            yield client, server
