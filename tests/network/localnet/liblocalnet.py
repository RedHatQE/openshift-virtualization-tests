import contextlib
import logging
import uuid
from typing import Generator

from kubernetes.client import ApiException
from kubernetes.dynamic import DynamicClient

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.vmspec import IP_ADDRESS, add_volume_disk, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Devices, Interface, Metadata, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.label_selector import LabelSelector
from utilities.constants import OVS_BRIDGE, WORKER_NODE_LABEL_KEY

LOCALNET_BR_EX_NETWORK = "localnet-br-ex-network"
LOCALNET_BR_EX_NETWORK_NO_VLAN = "localnet-br-ex-network-no-vlan"
LOCALNET_OVS_BRIDGE_NETWORK = "localnet-ovs-network"
LOCALNET_BR_EX_INTERFACE = "localnet-iface-vlan"
LOCALNET_BR_EX_INTERFACE_NO_VLAN = "localnet-iface-no-vlan"
LOCALNET_OVS_BRIDGE_INTERFACE = "localnet-iface-ovs-bridge"
LOCALNET_TEST_LABEL = {"test": "localnet"}
LINK_STATE_UP = "up"
LINK_STATE_DOWN = "down"
NNCP_INTERFACE_TYPE_ETHERNET = "ethernet"
LOGGER = logging.getLogger(__name__)


def run_vms(vms: tuple[BaseVirtualMachine, ...]) -> tuple[BaseVirtualMachine, ...]:
    for vm in vms:
        try:
            vm.start()  # type: ignore[no-untyped-call]
        except ApiException as vm_exception:
            if "VM is already running" in vm_exception.body:
                LOGGER.warning(f"VM {vm.name} is already running")
                continue
    for vm in vms:
        vm.wait_for_ready_status(status=True)  # type: ignore[no-untyped-call]
        vm.wait_for_agent_connected()
    return vms


def create_traffic_server(vm: BaseVirtualMachine) -> TcpServer:
    return TcpServer(vm=vm, port=IPERF_SERVER_PORT)


def create_traffic_client(
    server_vm: BaseVirtualMachine, client_vm: BaseVirtualMachine, spec_logical_network: str
) -> TcpClient:
    return TcpClient(
        vm=client_vm,
        server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
        server_port=IPERF_SERVER_PORT,
    )


def localnet_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    networks: list[Network],
    interfaces: list[Interface],
    network_data: cloudinit.NetworkData,
) -> BaseVirtualMachine:
    """
    Create a Fedora-based Virtual Machine connected to localnet network(s).

    The VM will:
    - Apply a specific label for anti-affinity scheduling.
    - Based on a standard Fedora VM template.

    Args:
        namespace (str): The namespace where the VM should be created.
        name (str): The name of the VM.
        client (DynamicClient): The Kubernetes dynamic client for resource creation.
        networks (list[Network]): List of Network objects defining the networks to attach.
            Each Network should have a name and configuration.
        interfaces (list[Interface]): List of Interface objects defining the interface configurations.
            Each Interface should have a name matching a Network, and additional configuration and state.
        network_data (cloudinit.NetworkData): Cloud-init NetworkData object containing the network
            configuration for the VM interfaces.

    Returns:
        BaseVirtualMachine: The configured VM object ready for creation.

    Example:
        >>> networks = [
        ...     Network(name="net1", multus=Multus(networkName="physical-net1")),
        ...     Network(name="net2", multus=Multus(networkName="physical-net2")),
        ... ]
        >>> interfaces = [
        ...     Interface(name="net1", bridge={}, state="up"),
        ...     Interface(name="net2", bridge={}, state="up"),
        ... ]
        >>> network_data = cloudinit.NetworkData(ethernets={
        ...     "eth0": cloudinit.EthernetDevice(addresses=["172.16.1.1/24"]),
        ...     "eth1": cloudinit.EthernetDevice(addresses=["172.16.2.1/24"]),
        ... })
        >>> vm = localnet_vm(namespace="test-localnet", name="vm1", client=client,
        ...                   networks=networks, interfaces=interfaces, network_data=network_data)
    """
    spec = base_vmspec()
    spec.template.metadata = spec.template.metadata or Metadata()
    spec.template.metadata.labels = spec.template.metadata.labels or {}
    spec.template.metadata.labels.update(LOCALNET_TEST_LABEL)

    vmi_spec = spec.template.spec
    vmi_spec.networks = networks
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices()
    vmi_spec.domain.devices.interfaces = interfaces

    # Prevents cloud-init from overriding the default OS user credentials
    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=network_data),
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    vmi_spec = add_volume_disk(vmi_spec=vmi_spec, volume=volume, disk=disk)

    vmi_spec.affinity = new_pod_anti_affinity(label=next(iter(LOCALNET_TEST_LABEL.items())))
    vmi_spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].namespaceSelector = {}

    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


def localnet_cudn(
    name: str,
    match_labels: dict[str, str],
    physical_network_name: str,
    client: DynamicClient,
    vlan_id: int | None = None,
    mtu: int | None = None,
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
        client (DynamicClient): Dynamic client for resource creation.
        vlan_id (int|None): The VLAN ID to configure for the network. If None, no VLAN is configured.
        mtu (int): Optional customized MTU of the network.

    Returns:
        ClusterUserDefinedNetwork: The configured CUDN object ready for creation.
    """
    ipam = libcudn.Ipam(mode=libcudn.Ipam.Mode.DISABLED.value)
    vlan = (
        libcudn.Vlan(mode=libcudn.Vlan.Mode.ACCESS.value, access=libcudn.Access(id=vlan_id))
        if vlan_id is not None
        else None
    )
    localnet = libcudn.Localnet(
        role=libcudn.Localnet.Role.SECONDARY.value,
        physicalNetworkName=physical_network_name,
        vlan=vlan,
        ipam=ipam,
        mtu=mtu,
    )
    network = libcudn.Network(topology=libcudn.Network.Topology.LOCALNET.value, localnet=localnet)

    return libcudn.ClusterUserDefinedNetwork(
        name=name,
        namespace_selector=LabelSelector(matchLabels=match_labels),
        network=network,
        client=client,
    )


@contextlib.contextmanager
def create_nncp_localnet_on_secondary_node_nic(
    node_nic_name: str,
    client: DynamicClient,
    mtu: int | None = None,
) -> Generator[libnncp.NodeNetworkConfigurationPolicy, None, None]:
    """Create NNCP to configure an OVS bridge on a secondary NIC across all worker nodes.

    Note:
        This function assumes homogeneous hardware—all workers must have a NIC with
        the same name. The configuration is applied to all workers to support anti-affinity scheduled VMs.

    Args:
        node_nic_name: Name of the available NIC on all nodes.
        client: Dynamic client used to create and manage the NNCP resource.
        mtu: Optional MTU to configure on the physical NIC.

    Yields:
        The created NodeNetworkConfigurationPolicy.
    """
    bridge_name = f"localnet-ovs-br-{uuid.uuid4().hex[:16]}"
    interfaces = []

    if mtu:
        # Ensure the physical NIC MTU matches the network MTU
        interfaces.append(
            libnncp.Interface(
                name=node_nic_name,
                type=NNCP_INTERFACE_TYPE_ETHERNET,
                mtu=mtu,
                state=libnncp.Resource.Interface.State.UP,
            )
        )

    interfaces.append(
        libnncp.Interface(
            name=bridge_name,
            type=OVS_BRIDGE,
            ipv4=libnncp.IPv4(enabled=False),
            ipv6=libnncp.IPv6(enabled=False),
            state=libnncp.Resource.Interface.State.UP,
            bridge=libnncp.Bridge(
                options=libnncp.BridgeOptions(libnncp.STP(enabled=False)),
                port=[
                    libnncp.Port(
                        name=node_nic_name,
                    )
                ],
            ),
        ),
    )

    desired_state = libnncp.DesiredState(
        interfaces=interfaces,
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_OVS_BRIDGE_NETWORK,
                bridge=bridge_name,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ]),
    )
    with libnncp.NodeNetworkConfigurationPolicy(
        client=client,
        name=bridge_name,
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp
