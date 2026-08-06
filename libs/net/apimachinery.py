from ipaddress import IPv4Interface, IPv6Interface
from typing import Any


def dict_normalization_for_dataclass(data: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a normalized dict from key-value pairs suitable for YAML serialization.

    Filters out None values, converts underscore-separated keys to dash-separated,
    and stringifies IP interface objects found in list values.

    Args:
        data: Sequence of (key, value) pairs representing dataclass fields.

    Returns:
        Normalized dict ready for YAML serialization.
    """
    return {
        key.replace("_", "-"): _ip_interfaces_to_str(val) if isinstance(val, list) else val
        for key, val in data
        if val is not None
    }


def _ip_interfaces_to_str(items: list[Any]) -> list[Any]:
    return [str(item) if isinstance(item, (IPv4Interface, IPv6Interface)) else item for item in items]
