import contextlib
import ipaddress
import logging
import shlex
import uuid
from collections.abc import Generator
from dataclasses import dataclass

from ocp_resources.pod import Pod
from pytest import Subtests
from timeout_sampler import retry

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.ip import filter_link_local_addresses, random_ipv4_address, random_ipv6_address
from libs.net.traffic_generator import (
    IPERF_SERVER_PORT,
    PodTcpClient,
    TcpServer,
    active_tcp_connections,
    is_tcp_connection,
)
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.bgp import CLUSTER_FRR_ASN, EXTERNAL_FRR_ASN, NET_TOOLS_CONTAINER_NAME

LOGGER = logging.getLogger(__name__)

EVPN_CUDN_NET_SEED: int = 5
CUDN_EVPN_SUBNET_IPV4: str = f"{random_ipv4_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0)}/24"
CUDN_EVPN_SUBNET_IPV6: str = f"{random_ipv6_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0)}/64"

_BRIDGE_NAME: str = "br0"
_VXLAN_NAME: str = "vxlan0"
_VXLAN_DEST_PORT: int = 4789

_L2_VID: int = 100
_L2_ENDPOINT_NETNS: str = "l2-ep"
_L2_VETH_POD_SIDE: str = "veth-l2-frr"
_L2_VETH_EP_SIDE: str = "veth-l2-ep"

_L3_VID: int = 200
_L3_VRF_NAME: str = "vrf-blue"
_L3_SVI_NAME: str = f"{_BRIDGE_NAME}.{_L3_VID}"
_L3_ENDPOINT_NETNS: str = "l3-ep"
_L3_VETH_POD_SIDE: str = "veth-l3-frr"
_L3_VETH_EP_SIDE: str = "veth-l3-ep"


@dataclass
class EvpnEndpoint:
    """External EVPN endpoint in a network namespace inside the FRR pod."""

    pod: Pod
    ip_addresses: list[str]
    netns_name: str
    mac_address: str | None = None


class EndpointTcpClient(PodTcpClient):
    """PodTcpClient that runs iperf3 inside a network namespace.

    'ip netns exec' replaces itself with iperf3 via execvp,
    so pgrep/pkill match by the bare iperf3 cmdline.

    Args:
        netns: Network namespace to run iperf3 in.
    """

    def __init__(
        self,
        pod: Pod,
        server_ip: str,
        server_port: int,
        netns: str,
        container: str | None = None,
    ) -> None:
        super().__init__(pod=pod, server_ip=server_ip, server_port=server_port, container=container)
        self._netns = netns

    def __enter__(self) -> EndpointTcpClient:
        run_cmd = f"ip netns exec {self._netns} {self._cmd}"
        self._pod.execute(
            command=["sh", "-c", f"nohup {run_cmd} >/tmp/iperf3.log 2>&1 &"],
            container=self._container,
        )
        self._ensure_is_running()
        return self


def cudn_evpn_subnets() -> list[str]:
    """Returns CUDN EVPN subnets based on cluster IP family support.

    Returns:
        List of subnet CIDRs (IPv4 and/or IPv6) supported by the cluster.
    """
    subnets = []
    if ipv4_supported_cluster():
        subnets.append(CUDN_EVPN_SUBNET_IPV4)
    if ipv6_supported_cluster():
        subnets.append(CUDN_EVPN_SUBNET_IPV6)
    return subnets


def deploy_evpn_bridge(
    pod: Pod,
    local_vtep_ip: str,
    remote_vtep_ips: list[str],
    l2_vni: int,
    l3_vni: int,
) -> None:
    """Creates the shared SVD bridge inside the FRR pod.

    Sets up a VLAN-filtering bridge with a single VXLAN device (SVD mode)
    and configures VLAN/VNI mappings for both L2 (MAC-VRF) and L3 (IP-VRF).

    Args:
        pod: The FRR pod.
        local_vtep_ip: FRR pod's IP used as local VTEP.
        remote_vtep_ips: Cluster node IPs for BUM traffic forwarding.
        l2_vni: MAC-VRF VNI for the L2 VLAN mapping.
        l3_vni: IP-VRF VNI for the L3 VLAN mapping.
    """
    commands = _build_bridge_commands(
        local_vtep_ip=local_vtep_ip, remote_vtep_ips=remote_vtep_ips, l2_vni=l2_vni, l3_vni=l3_vni
    )
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    LOGGER.info(f"EVPN SVD bridge deployed: {_BRIDGE_NAME} + {_VXLAN_NAME}")


def _build_bridge_commands(
    local_vtep_ip: str,
    remote_vtep_ips: list[str],
    l2_vni: int,
    l3_vni: int,
) -> list[str]:
    return [
        f"ip link add {_BRIDGE_NAME} type bridge vlan_filtering 1 vlan_default_pvid 0",
        f"ip link set {_BRIDGE_NAME} up",
        f"ip link add {_VXLAN_NAME} type vxlan dstport {_VXLAN_DEST_PORT} local {local_vtep_ip}"
        " nolearning external vnifilter",
        f"ip link set {_VXLAN_NAME} master {_BRIDGE_NAME}",
        f"bridge link set dev {_VXLAN_NAME} vlan_tunnel on neigh_suppress on learning off",
        f"ip link set {_VXLAN_NAME} up",
        *(f"bridge fdb append 00:00:00:00:00:00 dev {_VXLAN_NAME} dst {ip}" for ip in remote_vtep_ips),
        f"bridge vlan add dev {_BRIDGE_NAME} vid {_L2_VID} self",
        f"bridge vlan add dev {_VXLAN_NAME} vid {_L2_VID}",
        f"bridge vni add dev {_VXLAN_NAME} vni {l2_vni}",
        f"bridge vlan add dev {_VXLAN_NAME} vid {_L2_VID} tunnel_info id {l2_vni}",
        f"bridge vlan add dev {_BRIDGE_NAME} vid {_L3_VID} self",
        f"bridge vlan add dev {_VXLAN_NAME} vid {_L3_VID}",
        f"bridge vni add dev {_VXLAN_NAME} vni {l3_vni}",
        f"bridge vlan add dev {_VXLAN_NAME} vid {_L3_VID} tunnel_info id {l3_vni}",
    ]


def teardown_evpn_bridge(pod: Pod) -> None:
    """Removes the EVPN bridge from the FRR pod."""
    pod.execute(command=shlex.split(f"ip link delete {_BRIDGE_NAME}"), container=NET_TOOLS_CONTAINER_NAME)
    LOGGER.info(f"EVPN bridge removed: {_BRIDGE_NAME}")


def deploy_evpn_l2_endpoint(
    pod: Pod,
    endpoint_ips: list[str],
    mac_address: str | None = None,
) -> EvpnEndpoint:
    """Creates a stretched L2 endpoint on the shared SVD bridge.

    Creates a veth pair with the pod-side as an access port on the L2 VLAN,
    and the endpoint-side in a unique netns.

    Data path: VM -> OVN VXLAN (VNI) -> vxlan0 -> br0 (VLAN) -> veth -> netns.

    Args:
        pod: The FRR pod hosting the endpoint.
        endpoint_ips: IPs with prefix length (e.g. ["10.0.5.250/24", "fd00::fa/64"]).
        mac_address: Explicit MAC for the endpoint interface (locally-administered).

    Returns:
        EvpnEndpoint.
    """
    commands, netns = _build_l2_endpoint_commands(endpoint_ips=endpoint_ips, mac_address=mac_address)
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L2 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(pod=pod, ip_addresses=bare_ips, netns_name=netns, mac_address=mac_address)


def teardown_evpn_l2_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes the EVPN L2 endpoint (netns, veth) from the FRR pod.

    Args:
        endpoint: The endpoint to remove.
    """
    suffix = endpoint.netns_name.removeprefix(f"{_L2_ENDPOINT_NETNS}-")
    veth_pod = f"{_L2_VETH_POD_SIDE}-{suffix}"
    for cmd in [
        f"ip netns delete {endpoint.netns_name}",
        f"ip link delete {veth_pod}",
    ]:
        endpoint.pod.execute(command=shlex.split(cmd), container=NET_TOOLS_CONTAINER_NAME, ignore_rc=True)

    LOGGER.info(f"EVPN L2 endpoint removed: namespace={endpoint.netns_name}")


def _build_l2_endpoint_commands(
    endpoint_ips: list[str],
    mac_address: str | None = None,
) -> tuple[list[str], str]:
    suffix = uuid.uuid4().hex[:3]
    netns = f"{_L2_ENDPOINT_NETNS}-{suffix}"
    veth_pod = f"{_L2_VETH_POD_SIDE}-{suffix}"
    veth_ep = f"{_L2_VETH_EP_SIDE}-{suffix}"
    commands = [
        f"ip link add {veth_pod} type veth peer name {veth_ep}",
        f"ip link set {veth_pod} master {_BRIDGE_NAME}",
        f"bridge vlan add dev {veth_pod} vid {_L2_VID} pvid untagged",
        f"ip link set {veth_pod} up",
        f"ip netns add {netns}",
        f"ip link set {veth_ep} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {veth_ep}" for ip in endpoint_ips),
        *([f"ip netns exec {netns} ip link set dev {veth_ep} address {mac_address}"] if mac_address else []),
        f"ip netns exec {netns} ip link set {veth_ep} up",
        f"ip netns exec {netns} ip link set lo up",
    ]
    return commands, netns


def deploy_evpn_l3_vrf(pod: Pod, vni: int) -> None:
    """Creates the shared L3 VRF, SVI, and FRR BGP config on the external FRR pod.

    Args:
        pod: The external FRR pod.
        vni: IP-VRF VNI (must match UDN's ipVRF VNI).
    """
    commands = _build_l3_vrf_commands(vni=vni)
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    _configure_external_frr_l3_vrf(pod=pod, vni=vni)

    LOGGER.info(f"EVPN L3 VRF deployed: {_L3_VRF_NAME} VNI {vni}")


def teardown_evpn_l3_vrf(pod: Pod) -> None:
    """Removes the shared L3 VRF, SVI, and FRR BGP config."""
    for cmd in [
        f"ip link delete {_L3_SVI_NAME}",
        f"ip link delete {_L3_VRF_NAME}",
    ]:
        pod.execute(command=shlex.split(cmd), container=NET_TOOLS_CONTAINER_NAME, ignore_rc=True)

    pod.execute(
        command=["vtysh", "-c", "configure terminal", "-c", f"no router bgp {EXTERNAL_FRR_ASN} vrf {_L3_VRF_NAME}"],
        ignore_rc=True,
    )

    LOGGER.info(f"EVPN L3 VRF removed: {_L3_VRF_NAME}")


def _build_l3_vrf_commands(vni: int) -> list[str]:
    return [
        "sysctl -w net.ipv4.ip_forward=1",
        "sysctl -w net.ipv6.conf.all.forwarding=1",
        f"ip link add {_L3_VRF_NAME} type vrf table {vni}",
        f"ip link set {_L3_VRF_NAME} up",
        f"ip link add {_L3_SVI_NAME} link {_BRIDGE_NAME} type vlan id {_L3_VID}",
        f"ip link set {_L3_SVI_NAME} master {_L3_VRF_NAME}",
        f"ip link set {_L3_SVI_NAME} up",
    ]


def deploy_evpn_l3_endpoint(
    pod: Pod,
    endpoint_ips: list[str],
    gateway_ips: list[str],
) -> EvpnEndpoint:
    """Creates a routed L3 endpoint on the external FRR pod.

    Creates a veth pair (pod-side in VRF, endpoint-side in unique netns)
    with gateway IPs on the pod side and endpoint IPs in the netns.

    Data path: VM -> OVN L3 lookup -> VXLAN (IP-VRF VNI) -> vxlan0 -> br0 -> SVI -> VRF -> veth -> netns.

    Args:
        pod: The external FRR pod.
        endpoint_ips: IPs with prefix on a different subnet than CUDN (e.g. ["192.168.100.100/24"]).
        gateway_ips: Gateway IPs with prefix for the VRF veth side (e.g. ["192.168.100.1/24"]).

    Returns:
        EvpnEndpoint.
    """
    commands, netns = _build_l3_endpoint_commands(endpoint_ips=endpoint_ips, gateway_ips=gateway_ips)
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L3 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(pod=pod, ip_addresses=bare_ips, netns_name=netns)


def teardown_evpn_l3_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes the EVPN L3 endpoint (netns, veth) from the FRR pod.

    Args:
        endpoint: The endpoint to remove.
    """
    suffix = endpoint.netns_name.removeprefix(f"{_L3_ENDPOINT_NETNS}-")
    veth_pod = f"{_L3_VETH_POD_SIDE}-{suffix}"
    for cmd in [
        f"ip netns delete {endpoint.netns_name}",
        f"ip link delete {veth_pod}",
    ]:
        endpoint.pod.execute(command=shlex.split(cmd), container=NET_TOOLS_CONTAINER_NAME, ignore_rc=True)

    LOGGER.info(f"EVPN L3 endpoint removed: namespace={endpoint.netns_name}")


def _build_l3_endpoint_commands(
    endpoint_ips: list[str],
    gateway_ips: list[str],
) -> tuple[list[str], str]:
    suffix = uuid.uuid4().hex[:3]
    netns = f"{_L3_ENDPOINT_NETNS}-{suffix}"
    veth_pod = f"{_L3_VETH_POD_SIDE}-{suffix}"
    veth_ep = f"{_L3_VETH_EP_SIDE}-{suffix}"
    commands = [
        f"ip link add {veth_pod} type veth peer name {veth_ep}",
        f"ip link set {veth_pod} master {_L3_VRF_NAME}",
        *(f"ip addr add {ip} dev {veth_pod}" for ip in gateway_ips),
        f"ip link set {veth_pod} up",
        f"ip netns add {netns}",
        f"ip link set {veth_ep} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {veth_ep}" for ip in endpoint_ips),
        f"ip netns exec {netns} ip link set {veth_ep} up",
        f"ip netns exec {netns} ip link set lo up",
        *(
            f"ip netns exec {netns} ip {'-6' if ':' in ip else ''} route add default via {ip.split('/')[0]}"
            for ip in gateway_ips
        ),
    ]
    return commands, netns


def _configure_external_frr_l3_vrf(pod: Pod, vni: int) -> None:
    config = "\n".join([
        f"vrf {_L3_VRF_NAME}",
        f" vni {vni}",
        "exit-vrf",
        f"router bgp {EXTERNAL_FRR_ASN} vrf {_L3_VRF_NAME}",
        " address-family ipv4 unicast",
        "  redistribute connected",
        " exit-address-family",
        " address-family ipv6 unicast",
        "  redistribute connected",
        " exit-address-family",
        " address-family l2vpn evpn",
        f"  rd {EXTERNAL_FRR_ASN}:{vni}",
        f"  route-target import {CLUSTER_FRR_ASN}:{vni}",
        f"  route-target export {CLUSTER_FRR_ASN}:{vni}",
        "  advertise ipv4 unicast",
        "  advertise ipv6 unicast",
        " exit-address-family",
    ])
    pod.execute(command=["vtysh", "-c", "configure terminal", "-c", config])
    _wait_for_l3_vrf_routes(pod=pod)

    LOGGER.info(f"External FRR L3 VRF configured: {_L3_VRF_NAME} VNI {vni}")


@retry(wait_timeout=60, sleep=5, exceptions_dict={RuntimeError: []})
def _wait_for_l3_vrf_routes(pod: Pod) -> bool:
    output = pod.execute(
        command=shlex.split(f"ip route show vrf {_L3_VRF_NAME} proto bgp"),
        container=NET_TOOLS_CONTAINER_NAME,
    )
    if not output.strip():
        raise RuntimeError(f"VRF {_L3_VRF_NAME} has no BGP routes")
    return True


@contextlib.contextmanager
def evpn_workloads_active_connections(
    endpoint: EvpnEndpoint,
    vm: BaseVirtualMachine,
) -> Generator[list[tuple[EndpointTcpClient, TcpServer]]]:
    """Opens TCP connections for all IP families between an EVPN endpoint and a VM.

    Args:
        endpoint: EVPN endpoint (L2 or L3) running the TCP client (sends traffic).
        vm: VM running the TCP server (receives traffic).

    Yields:
        List of (EndpointTcpClient, TcpServer) tuples, one per IP family.
    """
    iface_name = lookup_primary_network(vm=vm).name
    iface = lookup_iface_status(vm=vm, iface_name=iface_name)
    server_ips = list(filter_link_local_addresses(ip_addresses=iface.ipAddresses))

    with contextlib.ExitStack() as stack:
        active_conns = []
        for server_ip in server_ips:
            active_conns.append(
                stack.enter_context(
                    cm=_evpn_workloads_connection(
                        endpoint=endpoint,
                        vm=vm,
                        server_ip=str(server_ip),
                    ),
                )
            )
        yield active_conns


@contextlib.contextmanager
def _evpn_workloads_connection(
    endpoint: EvpnEndpoint,
    vm: BaseVirtualMachine,
    server_ip: str,
) -> Generator[tuple[EndpointTcpClient, TcpServer]]:
    with TcpServer(vm=vm, port=IPERF_SERVER_PORT, bind_ip=server_ip) as tcp_server:
        with EndpointTcpClient(
            pod=endpoint.pod,
            server_ip=server_ip,
            server_port=IPERF_SERVER_PORT,
            netns=endpoint.netns_name,
            container=NET_TOOLS_CONTAINER_NAME,
        ) as tcp_client:
            yield tcp_client, tcp_server


def assert_evpn_workloads_connectivity(
    target_vm: BaseVirtualMachine,
    ref_vm: BaseVirtualMachine,
    l2_endpoint: EvpnEndpoint,
    l3_endpoint: EvpnEndpoint,
    subtests: Subtests,
) -> None:
    """Verifies EVPN connectivity: VM-to-VM, stretched L2, and routed L3.

    Args:
        target_vm: The under-test VM (server).
        ref_vm: The reference VM (client for VM-to-VM check).
        l2_endpoint: External L2 endpoint (client for stretched L2 check).
        l3_endpoint: External L3 endpoint (client for routed L3 check).
        subtests: pytest-subtests fixture for per-check reporting.
    """
    iface_name = lookup_primary_network(vm=target_vm).name

    with active_tcp_connections(
        client_vm=ref_vm,
        server_vm=target_vm,
        iface_name=iface_name,
    ) as vm_connections:
        for vm_client, vm_server in vm_connections:
            with subtests.test(f"VM-to-VM IPv{ipaddress.ip_address(vm_client.server_ip).version}"):
                assert is_tcp_connection(server=vm_server, client=vm_client)

    with evpn_workloads_active_connections(endpoint=l2_endpoint, vm=target_vm) as l2_connections:
        for l2_client, l2_server in l2_connections:
            with subtests.test(f"stretched-L2 IPv{ipaddress.ip_address(l2_client.server_ip).version}"):
                assert is_tcp_connection(server=l2_server, client=l2_client)

    with evpn_workloads_active_connections(endpoint=l3_endpoint, vm=target_vm) as l3_connections:
        for l3_client, l3_server in l3_connections:
            with subtests.test(f"routed-L3 IPv{ipaddress.ip_address(l3_client.server_ip).version}"):
                assert is_tcp_connection(server=l3_server, client=l3_client)
