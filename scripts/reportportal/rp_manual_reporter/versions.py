"""Shared CNV version parsing for the manual reporter.

Both the cluster-detection path and the ``--bundle`` path need the same
major.minor derivation; keeping it in one place prevents the two copies from
drifting apart.
"""

from __future__ import annotations


def cnv_xy_version_from_version_string(version: str) -> str | None:
    """Derive a CNV major.minor version from a full CNV version or bundle string.

    Surrounding whitespace and a leading ``v``/``V`` prefix are stripped, so
    both ``"4.22.0"`` (HCO status version) and ``"v4.22.0.rhel9-102"`` (bundle)
    are accepted.

    Args:
        version: Version or bundle string, e.g. ``"v4.22.0.rhel9-102"``.

    Returns:
        The ``"<major>.<minor>"`` portion (e.g. ``"4.22"``), or None when the
        input carries no usable major.minor pair (``""`` input, a single
        component such as ``"4"``, an empty component such as ``"4."`` or
        ``".22"``, or a non-numeric component such as ``"foo.bar"`` or a
        non-ASCII digit).
    """
    if not version:
        return None
    components = version.strip().lstrip("vV").split(".")
    if len(components) < 2:
        return None
    major, minor = components[0], components[1]
    if not (major.isascii() and major.isdigit() and minor.isascii() and minor.isdigit()):
        return None
    return f"{major}.{minor}"
