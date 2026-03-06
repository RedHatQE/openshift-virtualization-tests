import ipaddress
import random
from functools import cache
from typing import Final

_MAX_NUM_OF_RANDOM_OCTETS_PER_SESSION: Final[int] = 16
_MAX_NUM_OF_RANDOM_HEXTETS_PER_SESSION: Final[int] = 16
_IPV4_ADDRESS_SUBNET_PREFIX_VMI: Final[str] = "172.16"
_IPV6_ADDRESS_SUBNET_PREFIX_VMI: Final[str] = "fd00:1234:5678"
TCP_HEADER_SIZE: Final[int] = 20
IPV4_HEADER_SIZE: Final[int] = 20
IPV6_HEADER_SIZE: Final[int] = 40
ICMP_HEADER_SIZE: Final[int] = 8


def random_ipv4_address(net_seed: int, host_address: int) -> str:
    """Construct a random IPv4 address using a cached list of random third octets.

    Uses a pre-defined network address, a cached random third octet and the given
    host address to generate deterministic yet randomized IPv4 addresses.

    Args:
        net_seed (int): The index used to select a random third octet from the cached list.
        host_address (int): The last (fourth) octet of the IPv4 address.

    Returns:
        str: A string representing a randomized IPv4 address.
    """
    third_octets = _random_octets(count=_MAX_NUM_OF_RANDOM_OCTETS_PER_SESSION)
    return f"{_IPV4_ADDRESS_SUBNET_PREFIX_VMI}.{third_octets[net_seed]}.{host_address}"


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


def random_ipv6_address(net_seed: int, host_address: int) -> str:
    """Construct a random IPv6 address using a cached list of random seventh hextets.

    Uses a pre-defined network prefix, a cached random seventh hextet and the given
    host address to generate deterministic yet randomized IPv6 addresses.

    Args:
        net_seed (int): The index used to select a random seventh hextet from the cached list.
        host_address (int): The last (eighth) hextet of the IPv6 address.

    Returns:
        str: A string representing a randomized IPv6 address.
    """
    seventh_hextets = _random_hextets(count=_MAX_NUM_OF_RANDOM_HEXTETS_PER_SESSION)
    return f"{_IPV6_ADDRESS_SUBNET_PREFIX_VMI}::{seventh_hextets[net_seed]:x}:{host_address:x}"


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


def ip_header_size(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> int:
    return IPV4_HEADER_SIZE if ip.version == 4 else IPV6_HEADER_SIZE
