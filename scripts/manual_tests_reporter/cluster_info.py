# Co-authored-by: Claude <noreply@anthropic.com>
"""Auto-fill run attributes from a connected cluster.

Queries the OpenShift cluster for architecture, versions, storage class,
and cluster identity. The attributes are attached to the manual test
results report as JUnit properties and Datadog tags.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.subscription import Subscription
from simple_logger.logger import get_logger
from urllib3.exceptions import HTTPError

from utilities.architecture import get_cluster_architecture
from utilities.cluster import cache_admin_client
from utilities.constants.namespaces import NamespacesNames
from utilities.exceptions import UnsupportedCPUArchitectureError
from utilities.infra import get_clusterversion, get_infrastructure
from utilities.storage import get_default_storage_class

LOGGER = get_logger(name=__name__)


@dataclass
class ClusterAttributes:
    """Run attributes auto-filled from a connected cluster.

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


def _extract_domain_from_api_url(api_url: str) -> str | None:
    """Extract the cluster domain from an API server URL.

    Parses the hostname from the URL and strips the ``api.`` prefix.

    Args:
        api_url: Full API server URL, e.g.
            ``"https://api.bm15a-tlv2.abi.cnv-qe.rhood.us:6443"``.

    Returns:
        Domain portion after ``api.``, e.g.
            ``"bm15a-tlv2.abi.cnv-qe.rhood.us"``, or None when the
            hostname cannot be parsed.
    """
    hostname = urlparse(url=api_url).hostname
    api_prefix = "api."
    if not hostname:
        return None
    if hostname.startswith(api_prefix):
        return hostname.removeprefix(api_prefix)
    return hostname


def get_cluster_attributes() -> ClusterAttributes:
    """Query the connected OpenShift cluster for run attributes.

    Returns:
        ClusterAttributes with as many fields filled as possible.
        Fields that couldn't be determined are left as None.

    Note:
        Each query catches AttributeError/KeyError/IndexError/TypeError on
        purpose: CR ``status`` shapes vary with cluster state (e.g. a
        partially-deployed HCO has no ``status.versions``), so these are
        remote-data conditions here, not programming errors. Connection
        failures (ConfigException/ApiException) are likewise expected when
        running without a reachable cluster.
    """
    attrs = ClusterAttributes()

    try:
        # Cluster-wide attribute auto-fill requires a cluster-scoped admin client;
        # correctness requires it here (read-only status queries, no per-test client reuse).
        client = cache_admin_client()
    except (OSError, AttributeError, TypeError, ConfigException, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to connect to cluster: {exc}")
        return attrs

    # Architecture
    # UnsupportedCPUArchitectureError: empty node list; TypeError: env var has
    # unexpected shape; ApiException: unreachable cluster.
    try:
        arch_set = get_cluster_architecture()
        attrs.arch = "multiarch" if len(arch_set) > 1 else next(iter(arch_set))
    except (AttributeError, KeyError, TypeError, UnsupportedCPUArchitectureError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get cluster architecture: {exc}")

    # OCP version
    # AttributeError/KeyError: ClusterVersion status.desired absent on a
    # cluster that is still rolling out; ApiException: unreachable cluster.
    try:
        cluster_version = get_clusterversion(client=client)
        attrs.ocp_version = cluster_version.instance.status.desired.version
    except (AttributeError, KeyError, TypeError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get OCP version: {exc}")

    # CNV version (HCO)
    # AttributeError/IndexError/KeyError: partially-deployed HCO has no
    # status.versions entry yet; ApiException: unreachable cluster.
    # utilities.hco.get_hco_version is NOT reused here: it depends on
    # pytest_testconfig (py_config["hco_cr_name"]), which is unavailable in a
    # standalone CLI run without a pytest --tc-file.
    try:
        hco = HyperConverged(
            client=client,
            namespace=NamespacesNames.OPENSHIFT_CNV,
            name="kubevirt-hyperconverged",
        )
        if hco.exists:
            hco_version = hco.instance.status.versions[0].version
            attrs.bundle = f"v{hco_version}"
            version_parts = hco_version.split(".")
            if len(version_parts) >= 2:
                attrs.cnv_xy_version = f"{version_parts[0]}.{version_parts[1]}"
    except (AttributeError, KeyError, IndexError, TypeError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get CNV/HCO version: {exc}")

    # Cluster name and domain
    # AttributeError/KeyError: infrastructureName/apiServerURL absent while
    # the Infrastructure CR status is still populating; ApiException: unreachable cluster;
    # ValueError: malformed apiServerURL (e.g. invalid IPv6 URL) from urlparse.
    try:
        infra = get_infrastructure(admin_client=client)
        attrs.cluster_name = infra.instance.status.infrastructureName
        api_url = infra.instance.status.apiServerURL
        if api_url:
            attrs.cluster_domain = _extract_domain_from_api_url(api_url=api_url)
    except (AttributeError, KeyError, TypeError, ValueError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get cluster infrastructure info: {exc}")

    # Default storage class
    # AttributeError/ValueError: no default storage class configured (e.g.
    # local-storage-only cluster); ApiException: unreachable cluster.
    try:
        default_sc = get_default_storage_class(client=client)
        attrs.storage_class = default_sc.name if default_sc else None
    except (AttributeError, KeyError, TypeError, ValueError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get default storage class: {exc}")

    # HCO subscription channel
    # AttributeError/KeyError: subscription spec.channel absent on a fresh
    # install; ApiException: unreachable cluster.
    try:
        for subscription in Subscription.get(client=client, namespace=NamespacesNames.OPENSHIFT_CNV):
            if "hco" in subscription.name.lower() or "kubevirt" in subscription.name.lower():
                attrs.channel = subscription.instance.spec.channel
                break
    except (AttributeError, KeyError, TypeError, ApiException, HTTPError) as exc:
        LOGGER.warning(f"Failed to get subscription channel: {exc}")

    LOGGER.info(f"Cluster attributes: {attrs}")
    return attrs


def cluster_attributes_to_run_attrs(cluster_attrs: ClusterAttributes) -> list[dict[str, str]]:
    """Convert cluster attributes to run attribute format.

    Args:
        cluster_attrs: Attributes from the connected cluster.

    Returns:
        List of attribute dicts, excluding None values.
    """
    mapping: dict[str, str | None] = {
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
