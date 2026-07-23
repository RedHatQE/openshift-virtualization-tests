import ipaddress
import random
from functools import cache
from typing import Final

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster, supported_cluster_ip_versions

_MAX_NUM_OF_RANDOM_OCTETS_PER_SESSION: Final[int] = 16
_MAX_NUM_OF_RANDOM_HEXTETS_PER_SESSION: Final[int] = 16
_IPV4_ADDRESS_SUBNET_PREFIX_VMI: Final[str] = "172.16"
_IPV6_ADDRESS_SUBNET_PREFIX_VMI: Final[str] = "fd00:1234:5678"
TCP_HEADER_SIZE: Final[int] = 20
_IPV4_HEADER_SIZE: Final[int] = 20
_IPV6_HEADER_SIZE: Final[int] = 40
ICMP_HEADER_SIZE: Final[int] = 8


def random_cidr_addresses_by_family(net_seed: int, host_address: int) -> list[str]:
    """Return CIDR-formatted addresses for each IP family supported by the cluster.

    This library uses /24 for IPv4 and /64 for IPv6 VM subnets, matching the
    subnet definitions in this module. VMs with the same net_seed share the
    same subnet, allowing direct L2 communication without routing. Only
    families supported by the cluster are included.

    Args:
        net_seed: Index into the cached pool of random network prefixes.
        host_address: Host portion of the address — must be unique per VM in the test.

    Returns:
        List of CIDR strings (e.g. ["192.168.1.1/24", "fd00::1/64"]).
    """
    addresses = []
    if ipv4_supported_cluster():
        addresses.append(random_ipv4_address(net_seed=net_seed, host_address=host_address))
    if ipv6_supported_cluster():
        addresses.append(random_ipv6_address(net_seed=net_seed, host_address=host_address))
    return addresses


def random_ipv4_address(net_seed: int, host_address: int, cidr_required: bool = True) -> str:
    """Construct a random IPv4 address using a cached list of random third octets.

    Uses a pre-defined network address, a cached random third octet and the given
    host address to generate deterministic yet randomized IPv4 addresses.

    Args:
        net_seed (int): The index used to select a random third octet from the cached list.
        host_address (int): The last (fourth) octet of the IPv4 address.
        cidr_required (bool): When True (default), appends /24 prefix length to the address.

    Returns:
        str: A randomized IPv4 address, optionally in CIDR notation.
    """
    third_octets = _random_octets(count=_MAX_NUM_OF_RANDOM_OCTETS_PER_SESSION)
    subnet_length = "/24" if cidr_required else ""
    return f"{_IPV4_ADDRESS_SUBNET_PREFIX_VMI}.{third_octets[net_seed]}.{host_address}{subnet_length}"


@cache
def _random_octets(count: int) -> list[int]:
    """Generate a list of random IPv4 octet values.

    Randomly selects unique integers between 1 and 253 (inclusive) to be used
    as the third octet in an IPv4 address.

    Args:
        count (int): The number of random octet values to generate.

    Returns:
        list[int]: A list of unique random integers representing octet values.
    """
    return random.sample(range(1, 254), count)


def random_ipv6_address(net_seed: int, host_address: int, cidr_required: bool = True) -> str:
    """Construct a random IPv6 address using a cached list of random seventh hextets.

    Uses a pre-defined network prefix, a cached random seventh hextet and the given
    host address to generate deterministic yet randomized IPv6 addresses.

    Args:
        net_seed (int): The index used to select a random seventh hextet from the cached list.
        host_address (int): The last (eighth) hextet of the IPv6 address.
        cidr_required (bool): When True (default), appends /64 prefix length to the address.

    Returns:
        str: A randomized IPv6 address, optionally in CIDR notation.
    """
    seventh_hextets = _random_hextets(count=_MAX_NUM_OF_RANDOM_HEXTETS_PER_SESSION)
    subnet_length = "/64" if cidr_required else ""
    return f"{_IPV6_ADDRESS_SUBNET_PREFIX_VMI}::{seventh_hextets[net_seed]:x}:{host_address:x}{subnet_length}"


@cache
def _random_hextets(count: int) -> list[int]:
    """Generate a list of random IPv6 hextet values.

    Randomly selects unique integers between 1 and 65533 (inclusive) to be used
    as the seventh hextet in an IPv6 address.

    Args:
        count (int): The number of random hextet values to generate.

    Returns:
        list[int]: A list of unique random integers representing hextet values.
    """
    return random.sample(range(1, 0xFFFE), count)


def filter_link_local_addresses(ip_addresses: list[str]) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Filter out link-local IP addresses from a list of IP address strings.

    Link-local addresses (169.254.0.0/16 for IPv4, fe80::/10 for IPv6) are
    automatically assigned and typically not used for inter-VM communication.

    Args:
        ip_addresses: List of IP address strings to filter.

    Returns:
        List of IP address objects with link-local addresses removed.
    """
    return [ip for addr in ip_addresses if not (ip := ipaddress.ip_interface(address=addr).ip).is_link_local]


def filter_cluster_unsupported_addresses(
    ip_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Filter out IP addresses whose family is not supported by the cluster.

    Args:
        ip_addresses: List of IP address objects to filter.

    Returns:
        List containing only addresses whose IP version is supported by the cluster.
    """
    return [ip for ip in ip_addresses if ip.version in supported_cluster_ip_versions()]


def ip_header_size(ip: ipaddress.IPv4Address | ipaddress.IPv6Address | str) -> int:
    addr = ipaddress.ip_address(ip) if isinstance(ip, str) else ip
    return _IPV4_HEADER_SIZE if addr.version == 4 else _IPV6_HEADER_SIZE


def have_same_ip_families(
    actual_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
    expected_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> bool:
    return {ip.version for ip in actual_ips} == {ip.version for ip in expected_ips}
