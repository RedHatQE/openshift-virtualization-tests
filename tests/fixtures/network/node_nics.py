import logging
import re
import shlex
from typing import TYPE_CHECKING

import pytest
from ocp_resources.node_network_state import NodeNetworkState

from utilities.constants.networking import LINUX_BRIDGE, OVS_BRIDGE
from utilities.data_utils import name_prefix
from utilities.infra import ExecCommandOnPod, get_node_selector_dict
from utilities.network import EthernetNetworkConfigurationPolicy

if TYPE_CHECKING:
    from ocp_resources.node import Node
    from ocp_resources.pod import Pod

LOGGER = logging.getLogger(__name__)

SRIOV_VF_IFACE_NAME_PATTERN = re.compile(r"v\d+$")


def _bridge_port_names(*, node_interface: dict) -> set[str]:
    """Return the port names that a bridge or bond interface aggregates."""
    ports = set()
    if node_interface["type"] in (OVS_BRIDGE, LINUX_BRIDGE):
        for bridge_port in node_interface.get("bridge", {}).get("port", []):
            ports.add(bridge_port["name"])
    elif node_interface["type"] == "bond":
        for bond_port in node_interface.get("link-aggregation", {}).get("port", []):
            ports.add(bond_port)
    return ports


def _occupy_bridge_ports(
    *,
    node_name: str,
    node_interface: dict,
    node_physical_nics: list[str],
    node_nics: dict[str, list[str]],
) -> None:
    """Mark the physical ports of a bridge/bond interface as occupied on the node."""
    for bridge_port in _bridge_port_names(node_interface=node_interface):
        if bridge_port not in node_physical_nics or bridge_port in node_nics["occupied"]:
            continue

        node_iface_type = node_interface["type"]
        LOGGER.warning(
            f"{node_name}:{bridge_port} is a port of {node_interface['name']} {node_iface_type} - adding it "
            f"to the node's occupied interfaces list."
        )
        node_nics["occupied"].append(bridge_port)
        if bridge_port in node_nics["available"]:
            node_nics["available"].remove(bridge_port)


def _is_physically_connected(*, utility_pods: list[Pod], node: Node, iface_name: str) -> bool:
    """Return whether the node NIC reports a carrier (link up)."""
    carrier_response = ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(
        command=f"nmcli -g WIRED-PROPERTIES.CARRIER device show {iface_name}"
    )
    if carrier_response.lower() != "on":
        LOGGER.warning(f"{node.name} {iface_name} link is down (response: {carrier_response})")
        return False

    return True


def _node_active_nics(
    *, node: Node, interfaces: list[dict], node_physical_nics: list[str], utility_pods: list[Pod]
) -> dict[str, list[str]]:
    """Classify the node physical NICs as available or occupied."""
    node_nics: dict[str, list[str]] = {"available": [], "occupied": []}
    for node_interface in interfaces:
        iface_name = node_interface["name"]
        #  Exclude SR-IOV (VFs) interfaces.
        if SRIOV_VF_IFACE_NAME_PATTERN.findall(iface_name):
            continue

        # If the interface is a bridge with physical ports, then these ports should be labeled as occupied.
        _occupy_bridge_ports(
            node_name=node.name,
            node_interface=node_interface,
            node_physical_nics=node_physical_nics,
            node_nics=node_nics,
        )

        if iface_name in node_nics["occupied"] or iface_name not in node_physical_nics:
            continue

        if not _is_physically_connected(utility_pods=utility_pods, node=node, iface_name=iface_name):
            continue

        if ipv4_addresses := node_interface.get("ipv4", {}).get("address"):
            LOGGER.warning(
                f"{node.name}:{iface_name} is already configured with IP addresses ({ipv4_addresses}) - "
                f"adding it to the node's occupied interfaces list."
            )
            node_nics["occupied"].append(iface_name)
        else:
            node_nics["available"].append(iface_name)

    return node_nics


@pytest.fixture(scope="session")
def node_physical_nics(workers_utility_pods):
    interfaces = {}
    for pod in workers_utility_pods:
        node = pod.instance.spec.nodeName
        output = pod.execute(
            command=shlex.split("bash -c \"nmcli dev s | grep -v unmanaged | grep ethernet | awk '{print $1}'\"")
        ).split("\n")
        interfaces[node] = list(filter(None, output))  # Filter out empty lines

    LOGGER.info(f"Nodes physical NICs: {interfaces}")
    return interfaces


@pytest.fixture(scope="session")
def nodes_active_nics(
    nmstate_dependent_placeholder,
    admin_client,
    workers,
    workers_utility_pods,
    node_physical_nics,
):
    """Get nodes active NICs. First NIC is management NIC.

    Returns:
        Worker node name mapped to its ``available`` and ``occupied`` NIC names.
    """
    # TODO: Add support for environments that do not have KNMstate installed. e.g: clouds
    nodes_nics = {}
    for node in workers:
        nns = NodeNetworkState(name=node.name, client=admin_client)
        nodes_nics[node.name] = _node_active_nics(
            node=node,
            interfaces=nns.interfaces,
            node_physical_nics=node_physical_nics[node.name],
            utility_pods=workers_utility_pods,
        )

    LOGGER.info(f"Nodes active NICs: {nodes_nics}")
    return nodes_nics


@pytest.fixture(scope="session")
def nodes_available_nics(nodes_active_nics):
    return {node: nodes_active_nics[node]["available"] for node in nodes_active_nics.keys()}


@pytest.fixture(scope="session")
def hosts_common_available_ports(nodes_available_nics):
    """
    Get list of common ports from nodes_available_nics.

    nodes_available_nics like
    [['ens3', 'ens4', 'ens6', 'ens5'],
    ['ens3', 'ens8', 'ens6', 'ens7'],
    ['ens3', 'ens8', 'ens6', 'ens7']]

    will return ['ens3', 'ens6']
    """
    nic_sets = [set(lst) for lst in nodes_available_nics.values()]
    if not nic_sets:
        LOGGER.warning("No available NICs found on any worker node.")
        return []

    nics_list = sorted(set.intersection(*nic_sets))
    if not nics_list:
        LOGGER.warning("No common NICs found across all nodes.")
        return []

    LOGGER.info(f"Hosts common available NICs: {nics_list}")
    return nics_list


@pytest.fixture(scope="session")
def worker_nodes_ipv4_false_secondary_nics(
    admin_client,
    nodes_available_nics,
    schedulable_nodes,
):
    """
    Function removes ipv4 from secondary nics.
    """
    for worker_node in schedulable_nodes:
        worker_nics = nodes_available_nics[worker_node.name]
        with EthernetNetworkConfigurationPolicy(
            name=f"disable-ipv4-{name_prefix(worker_node.name)}",
            client=admin_client,
            node_selector=get_node_selector_dict(node_selector=worker_node.hostname),
            interfaces_name=worker_nics,
        ):
            LOGGER.info(
                f"selected worker node - {worker_node.name} under NNCP selected NIC information - {worker_nics} "
            )
