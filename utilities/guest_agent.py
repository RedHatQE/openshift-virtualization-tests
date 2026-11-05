"""QEMU guest-agent helpers shared by Linux and Windows guests."""

from re import search


def guest_agent_version_parser(version_string: str) -> str:
    """Extract a QEMU guest-agent version from Linux or Windows version output.

    Args:
        version_string: Version output that may include a package name or suffix.

    Returns:
        Three-part version with an optional dot- or hyphen-separated build number.

    Raises:
        AttributeError: No supported version pattern is found in the input.
    """
    version_match = search(pattern=r"[0-9]+\.[0-9]+\.[0-9]+(?:[.|-][0-9]+)?", string=version_string)
    if version_match is None:
        raise AttributeError("No supported QEMU guest-agent version found in the input")
    return version_match.group(0)
