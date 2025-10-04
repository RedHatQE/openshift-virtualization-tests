import contextlib
from typing import Generator

from ocp_resources.node import Node

from libs.net.traffic_generator import Client, Server
from libs.net.vmspec import IP_ADDRESS, add_network_interface, add_volume_disk, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.label_selector import LabelSelector
from utilities.constants import WORKER_NODE_LABEL_KEY

LOCALNET_BR_EX_NETWORK = "localnet-br-ex-network"
LOCALNET_OVS_BRIDGE_NETWORK = "localnet-ovs-network"
LOCALNET_TEST_LABEL = {"test": "localnet"}
LINK_STATE_UP = "up"
LINK_STATE_DOWN = "down"
NNCP_INTERFACE_TYPE_OVS_BRIDGE = "ovs-bridge"
_IPERF_SERVER_PORT = 5201
ICMP_HEADER = 8
TCP_HEADER = 20
IP_HEADER = 20


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
    server_vm: BaseVirtualMachine,
    client_vm: BaseVirtualMachine,
    spec_logical_network: str,
    maximum_segment_size: int | None = None,
) -> Client:
    """
    Create an iperf3 traffic client for testing connectivity.

    Maximum Segment Size (MSS) is typically calculated as:
    MTU - network headers size (IP + TCP) in bytes

    Args:
        server_vm (BaseVirtualMachine): The virtual machine acting as the iperf3 server.
        client_vm (BaseVirtualMachine): The virtual machine that will run the iperf3 client.
        spec_logical_network (str): The logical network interface name used for traffic.
        maximum_segment_size (int): Optional mtu customization (by customizing mss) in bytes.

    Returns:
        Client: A configured traffic client ready to run iperf3 tests.
    """
    return Client(
        vm=client_vm,
        server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
        server_port=_IPERF_SERVER_PORT,
        maximum_segment_size=maximum_segment_size,
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
    name: str, match_labels: dict[str, str], vlan_id: int, physical_network_name: str, mtu: int | None = None
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
        vlan_id (int): The VLAN ID to configure for the network.
        physical_network_name (str): The name of the physical network to associate with the localnet configuration.
        mtu (int): Optional customized MTU of the network.

    Returns:
        ClusterUserDefinedNetwork: The configured CUDN object ready for creation.
    """
    ipam = libcudn.Ipam(mode=libcudn.Ipam.Mode.DISABLED.value)
    vlan = libcudn.Vlan(mode=libcudn.Vlan.Mode.ACCESS.value, access=libcudn.Access(id=vlan_id))
    localnet = libcudn.Localnet(
        role=libcudn.Localnet.Role.SECONDARY.value,
        physicalNetworkName=physical_network_name,
        vlan=vlan,
        ipam=ipam,
        mtu=mtu,
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


@contextlib.contextmanager
def create_nncp_localnet_on_secondary_node_nic(
    worker_node: Node, nodes_available_nics: dict[str, list[str]], mtu: int | None = None
) -> Generator[libnncp.NodeNetworkConfigurationPolicy, None, None]:
    bridge_name = "localnet-ovs-br"
    desired_state = libnncp.DesiredState(
        interfaces=[
            libnncp.Interface(
                name=bridge_name,
                type=NNCP_INTERFACE_TYPE_OVS_BRIDGE,
                mtu=mtu,
                ipv4=libnncp.IPv4(enabled=False),
                ipv6=libnncp.IPv6(enabled=False),
                state=libnncp.Resource.Interface.State.UP,
                bridge=libnncp.Bridge(
                    options=libnncp.BridgeOptions(libnncp.STP(enabled=False)),
                    port=[
                        libnncp.Port(
                            name=nodes_available_nics[worker_node.name][-1],
                        )
                    ],
                ),
            )
        ],
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_OVS_BRIDGE_NETWORK,
                bridge=bridge_name,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ]),
    )
    with libnncp.NodeNetworkConfigurationPolicy(
        name=bridge_name,
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp
