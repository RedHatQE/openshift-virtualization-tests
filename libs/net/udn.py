from __future__ import annotations

import json
from collections.abc import Generator
from typing import TYPE_CHECKING, Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.resource import Resource

from libs.vm.spec import Interface, NetBinding, Network
from utilities.infra import create_ns

if TYPE_CHECKING:
    from ocp_resources.pod import Pod

UDN_BINDING_DEFAULT_PLUGIN_NAME: Final[str] = "l2bridge"
UDN_PASST_CORE_BINDING_NAME: Final[str] = "passtBinding"


def udn_primary_network(name: str, binding: str) -> tuple[Interface, Network]:
    if binding == UDN_PASST_CORE_BINDING_NAME:
        interface = Interface(name=name, passtBinding={})
    else:
        interface = Interface(name=name, binding=NetBinding(name=binding))
    return interface, Network(name=name, pod={})


def create_udn_namespace(
    name: str,
    client: DynamicClient,
    labels: dict[str, str] | None = None,
) -> Generator[Namespace]:
    return create_ns(
        name=name,
        labels={"k8s.ovn.org/primary-user-defined-network": "", **(labels or {})},
        admin_client=client,
    )


def lookup_udn_pod_ip(pod: Pod) -> str:
    """Return the UDN IP address of a pod.

    Args:
        pod: The pod to query.

    Returns:
        The IP address from the UDN network attachment.
    """
    network_status_annotation = f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/network-status"
    network_status = json.loads(pod.instance.metadata.annotations[network_status_annotation])
    udn_entry = next(entry for entry in network_status if "udn" in entry["interface"])
    return udn_entry["ips"][0]
