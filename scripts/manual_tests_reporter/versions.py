"""CNV version-string parsing shared by the CLI and cluster collection.

Both the CLI bundle input (``--bundle v4.22.0.rhel9-102``) and the HCO
version read from a cluster (``4.22.0``) derive the same ``CNV_XY_VER``
tag, so the derivation lives here — cluster-free and importable everywhere
(``cluster_info`` module import resolves cluster architecture at import
time and is therefore guarded on hosts without a kubeconfig).
"""

from __future__ import annotations


def cnv_xy_version_from_version_string(version_string: str) -> str | None:
    """Derive the CNV major.minor (X.Y) version from a version string.

    Args:
        version_string: Bundle or HCO version string (e.g.
            ``v4.22.0.rhel9-102`` or ``4.22.0``).

    Returns:
        The major.minor version (e.g. ``4.22``), or None when the string
        carries no non-empty major.minor pair.
    """
    parts = version_string.strip().lstrip("vV").split(".")
    return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 and parts[0] and parts[1] else None
