"""Guest VM operating system utilities."""

from functools import cache


@cache
def guest_iface_name(ordinal: int) -> str:
    """Return guest VM interface name by ordinal position."""
    if ordinal < 1:
        raise ValueError(f"ordinal must be >= 1, got {ordinal}")
    return f"eth{ordinal - 1}"
