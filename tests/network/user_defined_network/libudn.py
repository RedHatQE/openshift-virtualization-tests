from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ocp_resources.resource import Resource

from libs.net.vmspec import IpNotFound

if TYPE_CHECKING:
    from ocp_resources.pod import Pod


def lookup_default_pod_ip(pod: Pod) -> str:
    """Return the default network IP address of a pod.

    Args:
        pod: The pod to query.

    Returns:
        The IP address from the default network attachment.
    """
    network_status_annotation = f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/network-status"
    network_status = json.loads(pod.instance.metadata.annotations[network_status_annotation])
    default_entry = next(entry for entry in network_status if entry.get("default"))
    if not default_entry["ips"]:
        raise IpNotFound(f"No IPs assigned to default UDN entry on pod {pod.name}")
    return str(default_entry["ips"][0])
