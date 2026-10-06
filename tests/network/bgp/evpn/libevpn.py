import contextlib
import ipaddress
import json
import logging
import shlex
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from kubernetes.client.exceptions import ApiException
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
from tests.network.libs.bgp import (
    EVPN_MAC_VRF_VNI,
    NET_TOOLS_CONTAINER_NAME,
    OPENPE_CONTAINER_NAME,
    OPENPE_L3_VRF_NAME,
    openpe_l2_bridge_name,
    wait_for_openpe_interface,
)
from utilities.constants.timeouts import TIMEOUT_30SEC
from utilities.data_collector import get_data_collector_dir, write_to_file

if TYPE_CHECKING:
    from ocp_resources.node import Node

LOGGER = logging.getLogger(__name__)

EVPN_CUDN_NET_SEED: int = 5
CUDN_EVPN_SUBNET_IPV4: str = str(random_ipv4_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0))
CUDN_EVPN_SUBNET_IPV6: str = str(random_ipv6_address(net_seed=EVPN_CUDN_NET_SEED, host_address=0))

_L2_ENDPOINT_NETNS: str = "l2-ep"
_L2_VETH_POD_SIDE: str = "veth-l2-frr"
_L2_VETH_EP_SIDE: str = "veth-l2-ep"

_L3_ENDPOINT_NETNS: str = "l3-ep"
_L3_VETH_POD_SIDE: str = "veth-l3-frr"
_L3_VETH_EP_SIDE: str = "veth-l3-ep"

_PACKET_CAPTURE_FILTER: Final[str] = f"arp or icmp6 or (tcp port {IPERF_SERVER_PORT})"
_PACKET_CAPTURE_LIMIT: Final[int] = 100
_SERIAL_GETTY_DROP_IN_DIRECTORY: Final[str] = "/etc/systemd/system/serial-getty@ttyS0.service.d"
_SERIAL_GETTY_DROP_IN_FILE: Final[str] = f"{_SERIAL_GETTY_DROP_IN_DIRECTORY}/no-start-limit.conf"


@dataclass
class EvpnEndpoint:
    """External EVPN endpoint in a network namespace inside the OpenPE ToR pod."""

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
        self._log_file = f"/tmp/iperf3-{netns}.log"

    def __enter__(self) -> EndpointTcpClient:
        run_cmd = f"ip netns exec {self._netns} {self._cmd}"
        self._pod.execute(
            command=["sh", "-c", f"nohup {run_cmd} >{self._log_file} 2>&1 &"],
            container=self._container,
        )
        self._ensure_is_running()
        return self


def disable_vm_serial_getty_start_limit(vm: BaseVirtualMachine) -> None:
    """Disable serial-getty restart throttling in an EVPN test VM.

    EVPN connectivity setup checks multiple IPv4 and IPv6 iperf processes by
    opening short-lived serial-console sessions. Each logout restarts the
    serial getty, so Fedora's default limit of five starts in ten seconds can
    leave the console unavailable for subsequent connectivity checks.

    Args:
        vm: Fedora VM whose serial console is used by traffic generators.
    """
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
    mac_address: str | None = None,
) -> EvpnEndpoint:
    """Creates a stretched L2 endpoint on the OpenPE managed MAC-VRF bridge.

    Creates a veth pair with the pod-side attached to the OpenPE managed bridge
    and the endpoint-side in a unique netns.

    Data path: VM -> OVN VXLAN (VNI) -> OpenPE VXLAN -> br-hs-{vni} -> veth -> netns.

    Args:
        pod: The OpenPE ToR pod hosting the endpoint.
        endpoint_ips: IPs with prefix length (e.g. ["10.0.5.250/24", "fd00::fa/64"]).
        mac_address: Explicit MAC for the endpoint interface (locally-administered).

    Returns:
        EvpnEndpoint.
    """
    wait_for_openpe_interface(pod=pod, iface_name=openpe_l2_bridge_name(vni=EVPN_MAC_VRF_VNI))
    commands, netns = _build_l2_endpoint_commands(endpoint_ips=endpoint_ips, mac_address=mac_address)
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L2 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(pod=pod, ip_addresses=bare_ips, netns_name=netns, mac_address=mac_address)


def teardown_evpn_l2_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes the EVPN L2 endpoint (netns, veth) from the OpenPE ToR pod.

    Args:
        endpoint: The endpoint to remove.
    """
    endpoint.pod.execute(
        command=shlex.split(f"ip netns delete {endpoint.netns_name}"),
        container=NET_TOOLS_CONTAINER_NAME,
        ignore_rc=True,
    )
    LOGGER.info(f"EVPN L2 endpoint removed: namespace={endpoint.netns_name}")


def _build_l2_endpoint_commands(
    endpoint_ips: list[str],
    mac_address: str | None = None,
) -> tuple[list[str], str]:
    suffix = uuid.uuid4().hex[:3]
    netns = f"{_L2_ENDPOINT_NETNS}-{suffix}"
    veth_pod = f"{_L2_VETH_POD_SIDE}-{suffix}"
    veth_ep = f"{_L2_VETH_EP_SIDE}-{suffix}"
    bridge_name = openpe_l2_bridge_name(vni=EVPN_MAC_VRF_VNI)
    commands = [
        f"ip link add {veth_pod} type veth peer name {veth_ep}",
        f"ip link set {veth_pod} master {bridge_name}",
        f"ip link set {veth_pod} up",
        f"ip netns add {netns}",
        f"ip link set {veth_ep} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {veth_ep}" for ip in endpoint_ips),
        *([f"ip netns exec {netns} ip link set dev {veth_ep} address {mac_address}"] if mac_address else []),
        f"ip netns exec {netns} ip link set {veth_ep} up",
        f"ip netns exec {netns} ip link set lo up",
    ]
    return commands, netns


def _packet_capture_paths(endpoint: EvpnEndpoint) -> tuple[str, str]:
    capture_name = f"evpn-{endpoint.netns_name}-packets"
    capture_log = f"/tmp/{capture_name}.log"
    capture_pid = f"/tmp/{capture_name}.pid"
    return capture_log, capture_pid


def _start_packet_capture(
    endpoint: EvpnEndpoint,
    container: str,
    command: str,
) -> None:
    try:
        endpoint.pod.execute(
            command=["sh", "-c", command],
            container=container,
            ignore_rc=True,
        )
    except (ApiException, ExecOnPodError) as diagnostic_exception:
        LOGGER.warning(f"Failed to start EVPN packet capture in {container}: {diagnostic_exception}")


def _stop_packet_capture(endpoint: EvpnEndpoint, container: str, pid_path: str) -> None:
    try:
        endpoint.pod.execute(
            command=["sh", "-c", f'if [ -s {pid_path} ]; then kill "$(cat {pid_path})" 2>/dev/null || true; fi'],
            container=container,
            ignore_rc=True,
        )
    except (ApiException, ExecOnPodError) as diagnostic_exception:
        LOGGER.warning(f"Failed to stop EVPN packet capture in {container}: {diagnostic_exception}")


@contextlib.contextmanager
def _capture_evpn_packets(endpoint: EvpnEndpoint) -> Generator[None]:
    """Captures endpoint traffic in the OpenPE pod network namespace.

    Capture starts before the TCP client so a failing handshake, ARP request,
    or IPv6 neighbor discovery is available to the failure collector.
    Captures are bounded to avoid affecting successful tests.

    Args:
        endpoint: External EVPN endpoint whose traffic is captured.

    Yields:
        None while packet capture is active.
    """
    capture_log, capture_pid = _packet_capture_paths(endpoint=endpoint)
    packet_filter = shlex.quote(s=_PACKET_CAPTURE_FILTER)
    capture_command = (
        f"rm -f {capture_log} {capture_pid}; "
        "if command -v tcpdump >/dev/null 2>&1; then "
        f"nohup tcpdump -i any -nn -vvv -l -c {_PACKET_CAPTURE_LIMIT} {packet_filter} "
        f">{capture_log} 2>&1 & echo $! >{capture_pid}; "
        f"else echo 'tcpdump is unavailable in the pod network namespace' >{capture_log}; fi"
    )

    LOGGER.info(f"Starting EVPN packet capture for endpoint namespace {endpoint.netns_name}")
    _start_packet_capture(endpoint=endpoint, container=NET_TOOLS_CONTAINER_NAME, command=capture_command)
    try:
        yield
    finally:
        _stop_packet_capture(endpoint=endpoint, container=NET_TOOLS_CONTAINER_NAME, pid_path=capture_pid)


def deploy_evpn_l3_endpoint(
    pod: Pod,
    endpoint_ips: list[str],
    gateway_ips: list[str],
) -> EvpnEndpoint:
    """Creates a routed L3 endpoint on the OpenPE ToR pod.

    Creates a veth pair (pod-side in the OpenPE L3 VRF, endpoint-side in unique netns)
    with gateway IPs on the pod side and endpoint IPs in the netns.

    Data path: VM -> OVN L3 lookup -> VXLAN (IP-VRF VNI) -> OpenPE VRF -> veth -> netns.

    Args:
        pod: The OpenPE ToR pod.
        endpoint_ips: IPs with prefix on a different subnet than CUDN (e.g. ["192.168.100.100/24"]).
        gateway_ips: Gateway IPs with prefix for the VRF veth side (e.g. ["192.168.100.1/24"]).

    Returns:
        EvpnEndpoint.
    """
    wait_for_openpe_interface(pod=pod, iface_name=OPENPE_L3_VRF_NAME)
    commands, netns = _build_l3_endpoint_commands(endpoint_ips=endpoint_ips, gateway_ips=gateway_ips)
    for command in commands:
        pod.execute(command=shlex.split(command), container=NET_TOOLS_CONTAINER_NAME)

    bare_ips = [ip.split("/")[0] for ip in endpoint_ips]
    LOGGER.info(f"EVPN L3 endpoint deployed: {bare_ips} in namespace {netns}")

    return EvpnEndpoint(pod=pod, ip_addresses=bare_ips, netns_name=netns)


def teardown_evpn_l3_endpoint(endpoint: EvpnEndpoint) -> None:
    """Removes the EVPN L3 endpoint (netns, veth) from the OpenPE ToR pod.

    Args:
        endpoint: The endpoint to remove.
    """
    endpoint.pod.execute(
        command=shlex.split(f"ip netns delete {endpoint.netns_name}"),
        container=NET_TOOLS_CONTAINER_NAME,
        ignore_rc=True,
    )
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
        f"ip link set {veth_pod} master {OPENPE_L3_VRF_NAME}",
        *(f"ip addr add {ip} dev {veth_pod}" for ip in gateway_ips),
        f"ip link set {veth_pod} up",
        f"ip netns add {netns}",
        f"ip link set {veth_ep} netns {netns}",
        *(f"ip netns exec {netns} ip addr add {ip} dev {veth_ep}" for ip in endpoint_ips),
        f"ip netns exec {netns} ip link set {veth_ep} up",
        f"ip netns exec {netns} ip link set lo up",
        *(
            f"ip netns exec {netns} ip {'-6' if ipaddress.ip_interface(ip).version == 6 else ''}"
            f" route add default via {ip.split('/')[0]}"
            for ip in gateway_ips
        ),
    ]
    return commands, netns


def _collect_evpn_failure_state(endpoint: EvpnEndpoint) -> None:
    """Collects the external ToR state before EVPN connection cleanup.

    The collector runs while the endpoint network namespace and its veth are
    still present. This preserves the OpenPE bridge, VXLAN, FRR, and endpoint
    state that would otherwise be removed by context-manager cleanup.

    Args:
        endpoint: External EVPN endpoint whose ToR state is collected.
    """
    capture_log, _ = _packet_capture_paths(endpoint=endpoint)
    diagnostic_commands = [
        (
            "OpenPE FRR",
            OPENPE_CONTAINER_NAME,
            (
                "vtysh -c 'show bgp summary' "
                "-c 'show bgp l2vpn evpn summary' "
                "-c 'show bgp l2vpn evpn route' "
                f"-c 'show bgp vrf {OPENPE_L3_VRF_NAME} ipv4 unicast' "
                f"-c 'show bgp vrf {OPENPE_L3_VRF_NAME} ipv6 unicast' "
                f"-c 'show ip route vrf {OPENPE_L3_VRF_NAME}' "
                f"-c 'show ipv6 route vrf {OPENPE_L3_VRF_NAME}' "
                "-c 'show evpn vni' "
                f"-c 'show evpn mac vni {EVPN_MAC_VRF_VNI}'; "
                "cat /etc/perouter/frr/frr.conf"
            ),
        ),
        (
            "OpenPE network",
            NET_TOOLS_CONTAINER_NAME,
            (
                "ip -br addr; ip -d link; ip route; ip -6 route; "
                "bridge link; bridge vlan show; bridge fdb show; ip neigh; ip -6 neigh; "
                f"cat {capture_log}"
            ),
        ),
        (
            "EVPN endpoint",
            NET_TOOLS_CONTAINER_NAME,
            (
                f"ip netns exec {endpoint.netns_name} ip -br addr; "
                f"ip netns exec {endpoint.netns_name} ip -d link; "
                f"ip netns exec {endpoint.netns_name} ip route; "
                f"ip netns exec {endpoint.netns_name} ip -6 route; "
                f"ip netns exec {endpoint.netns_name} ip neigh; "
                f"ip netns exec {endpoint.netns_name} ip -6 neigh; "
                f"ip netns exec {endpoint.netns_name} ss -tanp; "
                f"cat /tmp/iperf3-{endpoint.netns_name}.log"
            ),
        ),
    ]
    output_sections = []
    for title, container, command in diagnostic_commands:
        try:
            output = endpoint.pod.execute(
                command=["sh", "-c", command],
                container=container,
                ignore_rc=True,
            )
        except (ApiException, ExecOnPodError) as diagnostic_exception:
            output = f"Failed to collect {title}: {diagnostic_exception}"
        output_sections.append(f"## {title}\n$ {command}\n{output}\n")

    write_to_file(
        base_directory=get_data_collector_dir(),
        file_name="evpn_failure_state.txt",
        content="\n".join(output_sections),
    )


def assert_evpn_tcp_connection(
    endpoint: EvpnEndpoint,
    server: TcpServer,
    client: EndpointTcpClient,
    failure_callback: Callable[[], None] | None = None,
) -> None:
    """Asserts an EVPN TCP connection and collects ToR state on failure.

    Args:
        endpoint: External EVPN endpoint that originates the TCP connection.
        server: VM-side TCP server.
        client: Endpoint-side TCP client.
        failure_callback: Optional action to run after failure state collection
            and before connection cleanup.
    """
    try:
        connection_established = is_tcp_connection(server=server, client=client)
    except ApiException, ExecOnPodError:
        _collect_evpn_failure_state(endpoint=endpoint)
        if failure_callback:
            failure_callback()
        raise

    if not connection_established:
        _collect_evpn_failure_state(endpoint=endpoint)
        if failure_callback:
            failure_callback()

    assert connection_established, f"TCP connection to {client.server_ip}:{client.server_port} is not running"


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
        stack.enter_context(cm=_capture_evpn_packets(endpoint=endpoint))
        try:
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
        except ApiException, ExecOnPodError:
            _collect_evpn_failure_state(endpoint=endpoint)
            raise
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
                assert_evpn_tcp_connection(endpoint=l2_endpoint, server=l2_server, client=l2_client)

    with evpn_workloads_active_connections(endpoint=l3_endpoint, vm=target_vm) as l3_connections:
        for l3_client, l3_server in l3_connections:
            with subtests.test(f"routed-L3 IPv{ipaddress.ip_address(l3_client.server_ip).version}"):
                assert_evpn_tcp_connection(endpoint=l3_endpoint, server=l3_server, client=l3_client)


def node_primary_ipv4_interface(node: Node) -> ipaddress.IPv4Interface:
    """Return the primary IPv4 interface of a node.

    Args:
        node: The node to get the primary IPv4 interface of.

    Returns:
        The primary IPv4 interface of the node as an ipaddress.IPv4Interface object.
    """
    primary_ifaddr = json.loads(node.instance.metadata.annotations["k8s.ovn.org/node-primary-ifaddr"])
    return ipaddress.IPv4Interface(address=primary_ifaddr["ipv4"])
