import contextlib
import ipaddress
import json
import logging
import shlex
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.pod import Pod
from pytest import Subtests

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
from tests.network.bgp.evpn.utils import OPENPE_ROUTER_NAMESPACE, network_interface_names
from tests.network.libs.bgp import NET_TOOLS_CONTAINER_NAME
from utilities.constants.timeouts import TIMEOUT_30SEC

if TYPE_CHECKING:
    from ocp_resources.node import Node

LOGGER = logging.getLogger(__name__)

EVPN_CUDN_NET_SEED: int = 5
CUDN_EVPN_SUBNET_IPV4: str = str(random_ipv4_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0))
CUDN_EVPN_SUBNET_IPV6: str = str(random_ipv6_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0))
EVPN_MAC_VRF_VNI: int = 10100
EVPN_IP_VRF_VNI: int = 20102
_L2_ENDPOINT_PREFIX: str = "l2-endpt-"
_L2_ROUTER_VETH_PREFIX: str = "l2-openpe-"
_L3_ENDPOINT_PREFIX: str = "l3-endpt-"
_L3_ROUTER_VETH_PREFIX: str = "l3-openpe-"
_SERIAL_GETTY_DROP_IN_DIRECTORY: str = "/etc/systemd/system/serial-getty@ttyS0.service.d"
_SERIAL_GETTY_DROP_IN_FILE: str = f"{_SERIAL_GETTY_DROP_IN_DIRECTORY}/no-start-limit.conf"


@dataclass
class EvpnEndpoint:
    """External EVPN endpoint in a helper-owned network namespace."""

    pod: Pod
    ip_addresses: list[str]
    netns_name: str
    router_interface_name: str
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


def disable_vm_serial_getty_start_limit(vm: BaseVirtualMachine) -> None:
    """Disable serial-console restart throttling in an EVPN test VM.

    Repeated short-lived console sessions during dual-stack traffic checks
    can exhaust Fedora's serial-getty start limit. Reapply after a cold
    restart because container-disk guest changes do not persist.

    Args:
        vm: Fedora test VM whose serial console is used for traffic checks.
    """
    LOGGER.info(f"Disabling serial-getty start limiting in EVPN VM {vm.name}")
    configure_command = (
        f"sudo mkdir -p {_SERIAL_GETTY_DROP_IN_DIRECTORY} && "
        f"printf '%s\\n' '[Unit]' 'StartLimitIntervalSec=0' | "
        f"sudo tee {_SERIAL_GETTY_DROP_IN_FILE} >/dev/null && "
        "sudo systemctl daemon-reload"
    )
    verify_command = (
        "systemctl show serial-getty@ttyS0.service --property=StartLimitIntervalUSec --value | grep -Eq '^0(us)?$'"
    )
    vm.console(commands=[configure_command, verify_command], timeout=TIMEOUT_30SEC)


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


def deploy_evpn_l2_endpoint(
    pod: Pod,
    endpoint_ips: list[str],
    l2_vni: int,
    mac_address: str | None = None,
) -> EvpnEndpoint:
    """Creates a stretched-L2 endpoint on an OpenPERouter-managed bridge.

    Args:
        pod: The node-pinned endpoint helper pod.
        endpoint_ips: IPs with prefix length (e.g. ["10.0.5.250/24", "fd00::fa/64"]).
        l2_vni: MAC-VRF VNI of the OpenPERouter-managed bridge.
        mac_address: Explicit MAC for the endpoint interface.

    Returns:
        The deployed endpoint.
    """
    commands, netns, router_interface = _build_l2_endpoint_commands(
        endpoint_ips=endpoint_ips,
        l2_vni=l2_vni,
        mac_address=mac_address,
    )
    _deploy_endpoint_commands(
        pod=pod,
        commands=commands,
        netns_name=netns,
        router_interface_name=router_interface,
        endpoint_description="stretched-L2",
    )
    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L2 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(
        pod=pod,
        ip_addresses=bare_ips,
        netns_name=netns,
        router_interface_name=router_interface,
        mac_address=mac_address,
    )


def teardown_evpn_l2_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes an EVPN stretched-L2 endpoint.

    Args:
        endpoint: The endpoint to remove.
    """
    _delete_endpoint_links(
        pod=endpoint.pod,
        netns_name=endpoint.netns_name,
        router_interface_name=endpoint.router_interface_name,
    )
    LOGGER.info(f"EVPN L2 endpoint removed: namespace={endpoint.netns_name}")


def _build_l2_endpoint_commands(
    endpoint_ips: list[str],
    l2_vni: int,
    mac_address: str | None = None,
) -> tuple[list[str], str, str]:
    suffix = uuid.uuid4().hex[:3]
    netns = f"{_L2_ENDPOINT_PREFIX}{suffix}"
    router_interface = f"{_L2_ROUTER_VETH_PREFIX}{suffix}"
    endpoint_interface = f"{_L2_ENDPOINT_PREFIX}{suffix}"
    commands = [
        f"ip link add {router_interface} type veth peer name {endpoint_interface}",
        f"ip link set {router_interface} netns {OPENPE_ROUTER_NAMESPACE}",
        (f"ip netns exec {OPENPE_ROUTER_NAMESPACE} ip link set {router_interface} master br-pe-{l2_vni}"),
        f"ip netns exec {OPENPE_ROUTER_NAMESPACE} ip link set {router_interface} up",
        f"ip netns add {netns}",
        f"ip link set {endpoint_interface} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {endpoint_interface}" for ip in endpoint_ips),
        *([f"ip netns exec {netns} ip link set dev {endpoint_interface} address {mac_address}"] if mac_address else []),
        f"ip netns exec {netns} ip link set {endpoint_interface} up",
        f"ip netns exec {netns} ip link set lo up",
    ]
    return commands, netns, router_interface


def deploy_evpn_l3_endpoint(
    pod: Pod,
    endpoint_ips: list[str],
    gateway_ips: list[str],
    vrf_name: str,
) -> EvpnEndpoint:
    """Creates a routed-L3 endpoint in an OpenPERouter-managed VRF.

    Args:
        pod: The node-pinned endpoint helper pod.
        endpoint_ips: Endpoint IPs with prefix on a subnet distinct from the CUDN.
        gateway_ips: Gateway IPs with prefix for the router-side veth.
        vrf_name: OpenPERouter VRF that owns the routed-L3 interface.

    Returns:
        The deployed endpoint.
    """
    commands, netns, router_interface = _build_l3_endpoint_commands(
        endpoint_ips=endpoint_ips,
        gateway_ips=gateway_ips,
        vrf_name=vrf_name,
    )
    _deploy_endpoint_commands(
        pod=pod,
        commands=commands,
        netns_name=netns,
        router_interface_name=router_interface,
        endpoint_description="routed-L3",
    )
    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L3 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(
        pod=pod,
        ip_addresses=bare_ips,
        netns_name=netns,
        router_interface_name=router_interface,
    )


def teardown_evpn_l3_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes an EVPN routed-L3 endpoint.

    Args:
        endpoint: The endpoint to remove.
    """
    _delete_endpoint_links(
        pod=endpoint.pod,
        netns_name=endpoint.netns_name,
        router_interface_name=endpoint.router_interface_name,
    )
    LOGGER.info(f"EVPN L3 endpoint removed: namespace={endpoint.netns_name}")


def _build_l3_endpoint_commands(
    endpoint_ips: list[str],
    gateway_ips: list[str],
    vrf_name: str,
) -> tuple[list[str], str, str]:
    suffix = uuid.uuid4().hex[:3]
    netns = f"{_L3_ENDPOINT_PREFIX}{suffix}"
    router_interface = f"{_L3_ROUTER_VETH_PREFIX}{suffix}"
    endpoint_interface = f"{_L3_ENDPOINT_PREFIX}{suffix}"
    commands = [
        f"ip link add {router_interface} type veth peer name {endpoint_interface}",
        f"ip link set {router_interface} netns {OPENPE_ROUTER_NAMESPACE}",
        f"ip netns exec {OPENPE_ROUTER_NAMESPACE} ip link set {router_interface} master {vrf_name}",
        *(f"ip netns exec {OPENPE_ROUTER_NAMESPACE} ip addr add {ip} dev {router_interface}" for ip in gateway_ips),
        f"ip netns exec {OPENPE_ROUTER_NAMESPACE} ip link set {router_interface} up",
        f"ip netns add {netns}",
        f"ip link set {endpoint_interface} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {endpoint_interface}" for ip in endpoint_ips),
        f"ip netns exec {netns} ip link set {endpoint_interface} up",
        f"ip netns exec {netns} ip link set lo up",
        *(
            f"ip netns exec {netns} ip {'-6' if ipaddress.ip_interface(ip).version == 6 else ''}"
            f" route replace default via {ip.split('/')[0]}"
            for ip in gateway_ips
        ),
    ]
    return commands, netns, router_interface


def _deploy_endpoint_commands(
    pod: Pod,
    commands: list[str],
    netns_name: str,
    router_interface_name: str,
    endpoint_description: str,
) -> None:
    try:
        for command in commands:
            pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)
    except ExecOnPodError as error:
        _delete_endpoint_links(
            pod=pod,
            netns_name=netns_name,
            router_interface_name=router_interface_name,
        )
        raise RuntimeError(f"Failed to deploy EVPN {endpoint_description} endpoint") from error


def _delete_endpoint_links(pod: Pod, netns_name: str, router_interface_name: str) -> None:
    namespaces = {
        namespace["name"]
        for namespace in json.loads(
            pod.execute(command=["ip", "-j", "netns", "list"], container=NET_TOOLS_CONTAINER_NAME)
        )
    }
    errors: list[ExecOnPodError] = []
    for namespace_name in (OPENPE_ROUTER_NAMESPACE, None):
        if namespace_name and namespace_name not in namespaces:
            continue
        if router_interface_name in network_interface_names(pod=pod, netns_name=namespace_name):
            prefix = ["ip", "netns", "exec", namespace_name] if namespace_name else []
            try:
                pod.execute(
                    command=[*prefix, "ip", "link", "delete", router_interface_name],
                    container=NET_TOOLS_CONTAINER_NAME,
                )
            except ExecOnPodError as error:
                LOGGER.error(f"Failed to remove EVPN interface {router_interface_name}: {error}")
                errors.append(error)
    if netns_name in namespaces:
        try:
            pod.execute(command=["ip", "netns", "delete", netns_name], container=NET_TOOLS_CONTAINER_NAME)
        except ExecOnPodError as error:
            LOGGER.error(f"Failed to remove EVPN traffic namespace {netns_name}: {error}")
            errors.append(error)
    if errors:
        raise RuntimeError(f"Failed to clean up EVPN traffic namespace {netns_name}: {errors}") from errors[0]
    remaining_namespaces = json.loads(
        pod.execute(command=["ip", "-j", "netns", "list"], container=NET_TOOLS_CONTAINER_NAME)
    )
    if any(namespace["name"] == netns_name for namespace in remaining_namespaces):
        raise RuntimeError(f"EVPN traffic namespace {netns_name} still exists after cleanup")
    for namespace_name in (OPENPE_ROUTER_NAMESPACE, None):
        if namespace_name and namespace_name not in namespaces:
            continue
        if router_interface_name in network_interface_names(pod=pod, netns_name=namespace_name):
            raise RuntimeError(f"EVPN interface {router_interface_name} still exists after cleanup")


@contextlib.contextmanager
def evpn_workloads_active_connections(
    endpoint: EvpnEndpoint,
    vm: BaseVirtualMachine,
) -> Generator[list[tuple[EndpointTcpClient, TcpServer]]]:
    """Opens TCP connections for all IP families between an EVPN endpoint and a VM.

    Args:
        endpoint: EVPN endpoint (L2 or L3) running the TCP client.
        vm: VM running the TCP server.

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
                    )
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
        l2_endpoint: External L2 endpoint (client for stretched-L2 check).
        l3_endpoint: External L3 endpoint (client for routed-L3 check).
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


def node_primary_ipv4_interface(node: Node) -> ipaddress.IPv4Interface:
    """Return the primary IPv4 interface of a node.

    Args:
        node: The node to get the primary IPv4 interface of.

    Returns:
        The primary IPv4 interface of the node.
    """
    primary_ifaddr = json.loads(node.instance.metadata.annotations["k8s.ovn.org/node-primary-ifaddr"])
    return ipaddress.IPv4Interface(address=primary_ifaddr["ipv4"])
