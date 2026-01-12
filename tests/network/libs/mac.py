import random
from functools import cache
from typing import Final

_MAX_NUM_OF_RANDOM_MAC_RANGES_PER_SESSION: Final[int] = 16
_MAC_ADDRESS_PREFIX: Final[str] = "02:01"


def random_mac_range(range_seed: int) -> tuple[str, str]:
    """
    Generate a large MAC address range (similar size to KubeMacPool auto generated ranges).

    Args:
        range_seed (int): The index used to select random octets from the cached list.

    Returns:
        tuple[str, str]: A tuple of (range_start, range_end) covering ~16 million addresses.
    """
    third_octets = _random_mac_third_octets(count=_MAX_NUM_OF_RANDOM_MAC_RANGES_PER_SESSION)
    third_octet = third_octets[range_seed]

    range_start = f"{_MAC_ADDRESS_PREFIX}:{third_octet:02x}:00:00:00"
    range_end = f"{_MAC_ADDRESS_PREFIX}:{third_octet:02x}:ff:ff:ff"

    return range_start, range_end


@cache
def _random_mac_third_octets(count: int) -> list[int]:
    """
    Generate a list of random MAC address third octet values.

    Randomly selects unique integers between 1 and 253 (inclusive) to be used
    as the third octet in a MAC address range.

    Args:
        count (int): The number of random octet values to generate.

    Returns:
        list[int]: A list of unique random integers representing octet values.
    """
    return random.sample(range(1, 254), count)
