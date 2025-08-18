import ipaddress
from dataclasses import dataclass
from typing import Final

from ocp_resources.node_network_state import NodeNetworkState

from tests.network.libs.nodenetworkconfigurationpolicy import DEFAULT_OVN_EXTERNAL_BRIDGE
from utilities.infra import cache_admin_client

DEFAULT_ROUTE_DEST_V4: Final[str] = "0.0.0.0/0"


class NodeInterfaceNotFoundError(Exception):
    pass


class NodeDefaultRouteNotFoundError(Exception):
    pass


@dataclass
class BrExNetworkInfo:
    cidr_v4: str = ""
    gateway_v4: str = ""


def lookup_br_ex_network_info(node_name: str) -> BrExNetworkInfo:
    nns_state = NodeNetworkState(name=node_name, client=cache_admin_client()).instance.status.currentState
    br_ex_info = BrExNetworkInfo()

    for iface in nns_state.interfaces:
        if iface.name == DEFAULT_OVN_EXTERNAL_BRIDGE and iface.type == "ovs-interface":
            ipv4_address = iface.ipv4.address[0]
            ip, prefix = ipv4_address["ip"], ipv4_address["prefix-length"]
            cidr = str(ipaddress.IPv4Interface(f"{ip}/{prefix}").network)
            br_ex_info.cidr_v4 = cidr
            break
    else:
        raise NodeInterfaceNotFoundError(
            f"Interface '{DEFAULT_OVN_EXTERNAL_BRIDGE}' not found in NodeNetworkState for node '{node_name}'."
        )

    for route in nns_state.routes.config:
        if route.destination == DEFAULT_ROUTE_DEST_V4 and route["next-hop-interface"] == DEFAULT_OVN_EXTERNAL_BRIDGE:
            br_ex_info.gateway_v4 = route["next-hop-address"]
            break
    else:
        raise NodeDefaultRouteNotFoundError(
            f"Default route not found for interface '{DEFAULT_OVN_EXTERNAL_BRIDGE}' "
            f"in NodeNetworkState for node '{node_name}'."
        )

    return br_ex_info
