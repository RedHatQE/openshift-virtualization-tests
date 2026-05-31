from typing import Any


def dict_normalization_for_dataclass(data: list[tuple[str, Any]]) -> dict[str, Any]:
    """Filter out none values and converts key characters containing underscores into dashes."""
    return {key.replace("_", "-"): val for (key, val) in data if val is not None}
