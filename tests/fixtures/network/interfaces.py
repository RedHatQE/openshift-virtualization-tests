import logging
import re
import shlex

import pytest
from ocp_resources.node_network_state import NodeNetworkState

from utilities.constants.networking import LINUX_BRIDGE, OVS_BRIDGE
from utilities.data_utils import name_prefix
from utilities.infra import ExecCommandOnPod, get_node_selector_dict
from utilities.network import EthernetNetworkConfigurationPolicy

LOGGER = logging.getLogger(__name__)


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
    # TODO: Add support for environments that do not have KNMstate installed. e.g: clouds
    # TODO: Reduce cognitive complexity
    def _bridge_ports(node_interface):
        ports = set()
        if node_interface["type"] in (OVS_BRIDGE, LINUX_BRIDGE) and node_interface["bridge"].get("port"):
            for bridge_port in node_interface["bridge"]["port"]:
                ports.add(bridge_port["name"])
        elif node_interface["type"] == "bond" and node_interface["link-aggregation"].get("port"):
            for bridge_port in node_interface["link-aggregation"]["port"]:
                ports.add(bridge_port)
        return ports

    """
    Get nodes active NICs.
    First NIC is management NIC
    """
    nodes_nics = {}
    for node in workers:
        nodes_nics[node.name] = {"available": [], "occupied": []}
        nns = NodeNetworkState(name=node.name, client=admin_client)

        for node_iface in nns.interfaces:
            iface_name = node_iface["name"]
            #  Exclude SR-IOV (VFs) interfaces.
            if re.findall(r"v\d+$", iface_name):
                continue

            # If the interface is a bridge with physical ports, then these ports should be labeled as occupied.
            for bridge_port in _bridge_ports(node_interface=node_iface):
                if (
                    bridge_port in node_physical_nics[node.name]
                    and bridge_port not in nodes_nics[node.name]["occupied"]
                ):
                    node_iface_type = node_iface["type"]
                    LOGGER.warning(
                        f"{node.name}:{bridge_port} is a port of {iface_name} {node_iface_type} - adding it "
                        f"to the node's occupied interfaces list."
                    )
                    nodes_nics[node.name]["occupied"].append(bridge_port)
                    if bridge_port in nodes_nics[node.name]["available"]:
                        nodes_nics[node.name]["available"].remove(bridge_port)

            if iface_name in nodes_nics[node.name]["occupied"]:
                continue

            if iface_name not in node_physical_nics[node.name]:
                continue

            physically_connected = (
                ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
                .exec(command=f"nmcli -g WIRED-PROPERTIES.CARRIER device show {iface_name}")
                .lower()
            )
            if physically_connected != "on":
                LOGGER.warning(f"{node.name} {iface_name} link is down")
                continue

            if node_iface["ipv4"].get("address"):
                nodes_nics[node.name]["occupied"].append(iface_name)
            else:
                nodes_nics[node.name]["available"].append(iface_name)

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


@pytest.fixture(scope="session")
def nmstate_dependent_placeholder():
    """
    Placeholder fixture that serves as a dependency marker for fixtures that interact
    with NMState Custom Resources (NNCP, NNCE, NNS).

    This fixture is used by pytest_collection_modifyitems to automatically detect
    and mark tests that depend on NMState functionality.
    """
    return
