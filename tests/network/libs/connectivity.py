import ipaddress
import json
import logging
from typing import TYPE_CHECKING, Final

from timeout_sampler import TimeoutExpiredError, retry

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient
from libs.net.vmspec import IpNotFound
from libs.vm.vm import BaseVirtualMachine
from utilities.virt import vm_console_run_commands

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

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


def read_guest_interface_ipv4(
    vm: VirtualMachineForTests | BaseVirtualMachine,
    interface_name: str,
) -> ipaddress.IPv4Interface:
    """Retrieve the IPv4 address and prefix length of an interface from the VM guest OS.

    Args:
        vm: The virtual machine to query.
        interface_name: The name of the network interface (e.g., "eth0").

    Returns:
        IPv4 address with prefix length (e.g., 192.168.1.5/24).

    Raises:
        IpNotFound: If no IPv4 address is found or console output cannot be parsed.
    """
    cmd: Final[str] = f"ip -j -4 addr show {interface_name}"
    output = vm_console_run_commands(vm=vm, commands=[cmd], timeout=30)
    LOGGER.info(f"Command {cmd} output: {output[cmd]}")

    try:
        iface_info = json.loads(output[cmd][1])
    except (IndexError, json.JSONDecodeError) as err:
        raise IpNotFound(f"Failed to parse console JSON from VM {vm.name} for '{cmd}': {output[cmd]}") from err

    if iface_info and "addr_info" in iface_info[0]:
        for addr in iface_info[0]["addr_info"]:
            if addr["family"] == "inet":
                ip_str = addr["local"]
                prefix_len = addr["prefixlen"]
                return ipaddress.IPv4Interface(address=f"{ip_str}/{prefix_len}")

    raise IpNotFound(f"No IPv4 address found on {interface_name} in VM {vm.name}")
