import ipaddress
from typing import Final

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
