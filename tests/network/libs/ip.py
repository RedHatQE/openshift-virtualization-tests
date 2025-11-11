import random
from functools import cache
from typing import Final

_MAX_NUM_OF_RANDOM_OCTETS_PER_SESSION: Final[int] = 16
_IPV4_ADDRESS_SUBNET_PREFIX_VMI: Final[str] = "172.16"


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
