import contextlib
import logging
from typing import Generator

from kubernetes.client import ApiException
from kubernetes.dynamic import DynamicClient

from libs.net.traffic_generator import TcpServer
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.vmspec import IP_ADDRESS, add_volume_disk, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Devices, Interface, Metadata, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.label_selector import LabelSelector

LOCALNET_BR_EX_NETWORK = "localnet-br-ex-network"
LOCALNET_BR_EX_NETWORK_NO_VLAN = "localnet-br-ex-network-no-vlan"
LOCALNET_OVS_BRIDGE_NETWORK = "localnet-ovs-network"
LOCALNET_BR_EX_INTERFACE = "localnet-iface-vlan"
LOCALNET_BR_EX_INTERFACE_NO_VLAN = "localnet-iface-no-vlan"
LOCALNET_OVS_BRIDGE_INTERFACE = "localnet-iface-ovs-bridge"
LOCALNET_TEST_LABEL = {"test": "localnet"}
LINK_STATE_UP = "up"
LINK_STATE_DOWN = "down"
_IPERF_SERVER_PORT = 5201
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
    return TcpServer(vm=vm, port=_IPERF_SERVER_PORT)


def create_traffic_client(
    server_vm: BaseVirtualMachine, client_vm: BaseVirtualMachine, spec_logical_network: str
) -> TcpClient:
    return TcpClient(
        vm=client_vm,
        server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
        server_port=_IPERF_SERVER_PORT,
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
    vlan = (
        libcudn.Vlan(mode=libcudn.Vlan.Mode.ACCESS.value, access=libcudn.Access(id=vlan_id))
        if vlan_id is not None
        else None
    )
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
) -> Generator[tuple[TcpClient, TcpServer], None, None]:
    with TcpServer(vm=server_vm, port=port) as server:
        with TcpClient(
            vm=client_vm,
            server_ip=lookup_iface_status(vm=server_vm, iface_name=spec_logical_network)[IP_ADDRESS],
            server_port=port,
        ) as client:
            yield client, server
