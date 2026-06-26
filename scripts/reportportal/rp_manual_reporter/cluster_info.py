# Co-authored-by: Claude <noreply@anthropic.com>
"""Auto-fill ReportPortal launch attributes from a connected cluster.

Queries the OpenShift cluster for architecture, versions, storage class,
and cluster identity. All imports are lazy to avoid import failures when
no cluster is connected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)


@dataclass
class ClusterAttributes:
    """Launch attributes auto-filled from a connected cluster.

    Attributes:
        arch: CPU architecture (e.g., "amd64").
        ocp_version: OpenShift version (e.g., "4.22.0-ec.4").
        cnv_xy_version: CNV major.minor version (e.g., "4.22").
        bundle: Full CNV bundle version (e.g., "v4.22.0.rhel9-102").
        cluster_name: Cluster infrastructure name (e.g., "bm15a-tlv2").
        cluster_domain: Cluster base domain (e.g., "bm15a-tlv2.abi.cnv-qe.rhood.us").
        storage_class: Default storage class label (e.g., "OCS").
        channel: HCO subscription channel (e.g., "candidate").
    """

    arch: str | None = None
    ocp_version: str | None = None
    cnv_xy_version: str | None = None
    bundle: str | None = None
    cluster_name: str | None = None
    cluster_domain: str | None = None
    storage_class: str | None = None
    channel: str | None = None


def _extract_domain_from_api_url(api_url: str) -> str:
    """Extract the cluster domain from an API server URL.

    Parses the hostname from the URL and strips the ``api.`` prefix.

    Args:
        api_url: Full API server URL, e.g.
            ``"https://api.bm15a-tlv2.abi.cnv-qe.rhood.us:6443"``.

    Returns:
        Domain portion after ``api.``, e.g.
        ``"bm15a-tlv2.abi.cnv-qe.rhood.us"``.
    """
    hostname = urlparse(api_url).hostname or ""
    api_prefix = "api."
    if hostname.startswith(api_prefix):
        return hostname.removeprefix(api_prefix)
    return hostname


def get_cluster_attributes() -> ClusterAttributes:
    """Query the connected OpenShift cluster for launch attributes.

    All cluster utility imports are lazy to avoid import failures
    when no cluster is connected.

    Returns:
        ClusterAttributes with as many fields filled as possible.
        Fields that couldn't be determined are left as None.
    """
    from utilities.architecture import get_cluster_architecture
    from utilities.cluster import cache_admin_client
    from utilities.exceptions import UnsupportedCPUArchitectureError
    from utilities.infra import get_clusterversion, get_infrastructure
    from utilities.storage import get_default_storage_class

    attrs = ClusterAttributes()

    # Get admin client first — needed by most queries
    try:
        client = cache_admin_client()
    except (OSError, AttributeError, TypeError) as exc:
        LOGGER.warning(f"Failed to connect to cluster: {exc}")
        return attrs

    # Architecture
    try:
        arch_set = get_cluster_architecture()
        attrs.arch = "multiarch" if len(arch_set) > 1 else next(iter(arch_set))
    except (AttributeError, KeyError, TypeError, UnsupportedCPUArchitectureError) as exc:
        LOGGER.warning(f"Failed to get cluster architecture: {exc}")

    # OCP version
    try:
        cluster_version = get_clusterversion(client=client)
        attrs.ocp_version = cluster_version.instance.status.desired.version
    except (AttributeError, KeyError, TypeError) as exc:
        LOGGER.warning(f"Failed to get OCP version: {exc}")

    # CNV version (HCO)
    try:
        from ocp_resources.hyperconverged import HyperConverged

        hco = HyperConverged(
            client=client,
            namespace="openshift-cnv",
            name="kubevirt-hyperconverged",
        )
        if hco.exists:
            hco_version = hco.instance.status.versions[0].version
            attrs.bundle = f"v{hco_version}"
            version_parts = hco_version.split(".")
            if len(version_parts) >= 2:
                attrs.cnv_xy_version = f"{version_parts[0]}.{version_parts[1]}"
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        LOGGER.warning(f"Failed to get CNV/HCO version: {exc}")

    # Cluster name and domain
    try:
        infra = get_infrastructure(admin_client=client)
        attrs.cluster_name = infra.instance.status.infrastructureName
        api_url = infra.instance.status.apiServerURL
        if api_url:
            attrs.cluster_domain = _extract_domain_from_api_url(api_url=api_url)
    except (AttributeError, KeyError, TypeError) as exc:
        LOGGER.warning(f"Failed to get cluster infrastructure info: {exc}")

    # Default storage class
    try:
        default_sc = get_default_storage_class(client=client)
        attrs.storage_class = default_sc.name if default_sc else None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        LOGGER.warning(f"Failed to get default storage class: {exc}")

    # HCO subscription channel
    try:
        from ocp_resources.subscription import Subscription

        for sub in Subscription.get(client=client, namespace="openshift-cnv"):
            if "hco" in sub.name.lower() or "kubevirt" in sub.name.lower():
                attrs.channel = sub.instance.spec.channel
                break
    except (AttributeError, KeyError, TypeError) as exc:
        LOGGER.warning(f"Failed to get subscription channel: {exc}")

    LOGGER.info(f"Cluster attributes: {attrs}")
    return attrs


def cluster_attributes_to_launch_attrs(cluster_attrs: ClusterAttributes) -> list[dict[str, str]]:
    """Convert cluster attributes to RP launch attribute format.

    Args:
        cluster_attrs: Attributes from the connected cluster.

    Returns:
        List of attribute dicts for RPClient, excluding None values.
    """
    mapping: dict[str, Any] = {
        "ARCH": cluster_attrs.arch,
        "OCP": cluster_attrs.ocp_version,
        "CNV_XY_VER": cluster_attrs.cnv_xy_version,
        "BUNDLE": cluster_attrs.bundle,
        "CLUSTER_NAME": cluster_attrs.cluster_name,
        "CLUSTER_DOMAIN": cluster_attrs.cluster_domain,
        "SC": cluster_attrs.storage_class,
        "CHANNEL": cluster_attrs.channel,
    }
    return [{"key": key, "value": value} for key, value in mapping.items() if value is not None]
