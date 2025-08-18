from typing import Final

from ocp_resources.node_network_state import NodeNetworkState

from libs.net import netattachdef as libnad
from tests.network.libs.nodenetworkconfigurationpolicy import DEFAULT_OVN_EXTERNAL_BRIDGE
from utilities.infra import cache_admin_client

DEFAULT_ROUTE_V4: Final[libnad.IpamRoute] = libnad.IpamRoute(dst="0.0.0.0/0")


class NodeDefaultRouteNotFoundError(Exception):
    pass


def lookup_br_ex_gateway_v4(node_name: str) -> str:
    """
    Looks up the IPv4 gateway address of the default route for the specified node's external bridge.

    Args:
        node_name (str): The name of the node to look up.

    Returns:
        str: The IPv4 gateway address of the default route.
    """
    nns_state = NodeNetworkState(name=node_name, client=cache_admin_client()).instance.status.currentState

    for route in nns_state.routes.config:
        if route.destination == DEFAULT_ROUTE_V4.dst and route["next-hop-interface"] == DEFAULT_OVN_EXTERNAL_BRIDGE:
            return route["next-hop-address"]

    raise NodeDefaultRouteNotFoundError(
        f"Default route not found for interface '{DEFAULT_OVN_EXTERNAL_BRIDGE}' "
        f"in NodeNetworkState for node '{node_name}'."
    )
