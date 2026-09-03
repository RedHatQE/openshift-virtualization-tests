from __future__ import annotations

import json
import re
import shlex
from typing import TYPE_CHECKING

from ocp_resources.resource import Resource
from timeout_sampler import retry

from libs.net.vmspec import IpNotFound

if TYPE_CHECKING:
    from ocp_resources.pod import Pod


class PacketLossSummaryNotFoundError(Exception):
    """Raised when ping output does not contain a packet-loss summary line."""


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


def packet_loss_percent_from_ping_output(ping_output: str) -> float:
    """Return the packet-loss percentage parsed from ping summary output.

    Args:
        ping_output: The full output of a ping command.

    Returns:
        The packet-loss percentage (0-100) reported in the statistics line.

    Raises:
        PacketLossSummaryNotFoundError: If the ping output has no packet-loss summary line.
    """
    match = re.search(pattern=r"(\d+(?:\.\d+)?)% packet loss", string=ping_output)
    if not match:
        raise PacketLossSummaryNotFoundError(f"No packet-loss summary found in ping output: {ping_output}")
    return float(match.group(1))


@retry(wait_timeout=60, sleep=5, exceptions_dict={PacketLossSummaryNotFoundError: []})
def wait_for_expected_packet_loss(pod: Pod, ping_command: str, expected_packet_loss: float) -> bool:
    """Poll ping from a pod until the reported packet loss matches the expected value.

    Args:
        pod: The pod to run ping from.
        ping_command: The ping command to execute.
        expected_packet_loss: The packet-loss percentage (0-100) to wait for.

    Returns:
        True once the ping reports the expected packet loss.
    """
    ping_output = pod.execute(command=shlex.split(ping_command), timeout=15, ignore_rc=True)
    return packet_loss_percent_from_ping_output(ping_output=ping_output) == expected_packet_loss
