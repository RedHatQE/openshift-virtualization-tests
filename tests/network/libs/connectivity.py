import ipaddress
import re
from typing import Final

from timeout_sampler import TimeoutExpiredError, retry

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient
from libs.net.vmspec import lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine
from utilities.virt import vm_console_run_commands


class PacketLossSummaryNotFoundError(Exception):
    """Raised when ping output does not contain a packet-loss summary line."""


ARP_ISOLATION_SYSCTL_CMD: Final[list[str]] = [
    # Only answer ARP for the IP assigned to the receiving interface —
    # prevents eth1 from responding to ARP for eth2's IP when queried from the same VLAN.
    "sysctl -w net.ipv4.conf.all.arp_ignore=1",
    # Use the sender IP belonging to the outgoing interface in ARP requests,
    # preventing the peer from caching a wrong MAC for the wrong IP.
    "sysctl -w net.ipv4.conf.all.arp_announce=2",
]


def build_ping_command(dst_ip: str, count: int, timeout: int) -> str:
    """
    Build a ping command string that handles both IPv4 and IPv6 addresses.

    Args:
        dst_ip: Destination IP address to ping.
        count: Number of packets to send.
        timeout: Timeout in seconds.

    Returns:
        str: Ping command string ready to execute.
    """
    ip = ipaddress.ip_address(address=dst_ip)
    ping_ipv6_flag = " -6" if ip.version == 6 else ""
    return f"ping{ping_ipv6_flag} {dst_ip} -c {count} -w {timeout}"


def ping_between_vms(
    source_vm: BaseVirtualMachine,
    destination_vm: BaseVirtualMachine,
    iface_name: str = "default",
    ip_family: int = 4,
) -> str:
    """Ping the destination VM from the source VM over the given interface.

    The ping command is not validated by its exit code, so total packet loss is reflected
    in the returned output rather than raising.

    Args:
        source_vm: VM that initiates the ping.
        destination_vm: VM whose interface IP is the ping target.
        iface_name: Interface on the destination VM whose status IP is pinged
            ("default" is the pod network).
        ip_family: IP version to use (4 or 6).

    Returns:
        The raw ping output.
    """
    ping_timeout = 15
    dst_ip = lookup_iface_status_ip(vm=destination_vm, iface_name=iface_name, ip_family=ip_family)
    ping_command = build_ping_command(dst_ip=str(dst_ip), count=10, timeout=ping_timeout)
    output = vm_console_run_commands(
        vm=source_vm,
        commands=[ping_command],
        timeout=ping_timeout + 5,
        return_code_validation=False,
    )
    return "\n".join(output[ping_command])


@retry(wait_timeout=60, sleep=5, exceptions_dict={})
def poll_tcp_connectivity(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    server_ip: str,
    client_bind_dev: str | None = None,
    server_bind_dev: str | None = None,
    expect_connectivity: bool = True,
) -> bool:
    """Poll TCP connectivity (or its absence) between two VMs, retrying until the expected state is reached.

    Args:
        client_vm: VM initiating the TCP connection.
        server_vm: VM running the iperf3 server.
        server_ip: IP address the server binds to.
        client_bind_dev: Guest network device name to force the client out (e.g. "eth1").
            Bypasses ECMP routing when both secondary interfaces share the same subnet.
        server_bind_dev: Guest network device name to force the server responses out (e.g. "eth1").
            Bypasses ECMP routing on the server VM when it has multiple secondary interfaces.
        expect_connectivity: When True polls until connectivity exists; when False polls until it does not.

    Returns:
        True when the observed reachability matches expect_connectivity.
    """
    try:
        with TcpServer(vm=server_vm, port=IPERF_SERVER_PORT, bind_ip=server_ip, bind_dev=server_bind_dev):
            with VMTcpClient(
                vm=client_vm, server_ip=server_ip, server_port=IPERF_SERVER_PORT, bind_dev=client_bind_dev
            ):
                reachable = True
    except TimeoutExpiredError:
        reachable = False
    return reachable if expect_connectivity else not reachable


def packet_loss_percent_from_ping_output(ping_output: str) -> float:
    """Return the packet-loss percentage parsed from ping summary output.

    Args:
        ping_output: The full output of a ping command.

    Returns:
        The packet-loss percentage (0-100) reported in the statistics line.

    Raises:
        PacketLossSummaryNotFoundError: If the ping output has no packet-loss summary line.
    """
    match = re.search(pattern=r"(\d+(?:\.\d+)?)% packet loss", string=ping_output)
    if not match:
        raise PacketLossSummaryNotFoundError(f"No packet-loss summary found in ping output: {ping_output}")
    return float(match.group(1))


def is_destination_vm_pingable(
    source_vm: BaseVirtualMachine,
    destination_vm: BaseVirtualMachine,
) -> bool:
    """Return whether the destination VM is reachable by ping from the source VM.

    Reachability tolerates partial packet loss.

    Args:
        source_vm: VM that initiates the ping.
        destination_vm: VM whose interface IP is the ping target.

    Returns:
        True if any ping reply was received, False on total packet loss.
    """
    ping_output = ping_between_vms(source_vm=source_vm, destination_vm=destination_vm)
    return packet_loss_percent_from_ping_output(ping_output=ping_output) < 100
