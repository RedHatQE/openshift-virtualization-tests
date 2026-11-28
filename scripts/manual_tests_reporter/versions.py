"""CNV version-string parsing shared by the CLI and cluster collection.

Both the CLI bundle input (``--bundle v4.22.0.rhel9-102``) and the HCO
version read from a cluster (``4.22.0``) derive the same Datadog tag pair,
so the derivation lives here — cluster-free and importable everywhere
(``cluster_info`` module import resolves cluster architecture at import
time and is therefore guarded on hosts without a kubeconfig).
"""

from __future__ import annotations


def cnv_versions_from_version_string(version_string: str) -> tuple[str | None, str | None]:
    """Derive the CNV version attributes from a version string.

    Args:
        version_string: Bundle or HCO version string (e.g.
            ``v4.22.0.rhel9-102`` or ``4.22.0``).

    Returns:
        Tuple of (cnv_version, cnv_xy_version) — the full X.Y.Z version and
        the major.minor version, either None when the string lacks the
        needed non-empty components.
    """
    parts = version_string.strip().lstrip("vV").split(".")
    cnv_version = ".".join(parts[:3]) if len(parts) >= 3 and all(parts[:3]) else None
    cnv_xy_version = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 and parts[0] and parts[1] else None
    return cnv_version, cnv_xy_version
