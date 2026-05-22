import ipaddress
from typing import Final

from timeout_sampler import TimeoutExpiredError, retry

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient
from libs.vm.vm import BaseVirtualMachine

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
