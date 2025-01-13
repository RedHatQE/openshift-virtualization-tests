import ipaddress
import logging
import subprocess

import pytest
from ocp_resources.infrastructure import Infrastructure
from ocp_resources.node_network_configuration_policy import NNCPConfigurationFailed
from ocp_resources.node_network_state import NodeNetworkState
from timeout_sampler import TimeoutExpiredError

from utilities.constants import IPV4_STR, IPV6_STR, TIMEOUT_9MIN
from utilities.infra import get_node_selector_dict, label_nodes
from utilities.network import (
    IFACE_ABSENT_STATE,
    IFACE_UP_STATE,
    EthernetNetworkConfigurationPolicy,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)

LOGGER = logging.getLogger(__name__)

NODE_LABEL = {"capture": "allow"}
PRIMARY_NIC = "primary-nic"
IPV4_ADDRESSES = f"{IPV4_STR}_addresses"
IPV6_ADDRESSES = f"{IPV6_STR}_addresses"
PREFIX_LENGTH = "prefix-length"

pytestmark = pytest.mark.usefixtures("skip_if_ovn_cluster")


def remove_cluster_ingress_ip_from_addresses(addresses):
    keepalive_addr = get_cluster_ingress_ip()
    return [address for address in addresses if keepalive_addr not in address["ip"]]


def valid_routes(default_routes, bridge_routes):
    default_routes = {route["destination"] for route in default_routes["config"]}
    bridge_routes = {route["destination"] for route in bridge_routes["config"]}
    return default_routes.issubset(bridge_routes)


def valid_addresses(default_addresses, bridge_addresses, ip_family):
    if IPV6_STR in ip_family:
        for address in default_addresses:
            if ipaddress.ip_network(address["ip"]).is_link_local:
                continue
            if address not in bridge_addresses:
                return False
    else:
        default_addresses = remove_cluster_ingress_ip_from_addresses(addresses=default_addresses)
        bridge_addresses = remove_cluster_ingress_ip_from_addresses(addresses=bridge_addresses)
        if default_addresses != bridge_addresses:
            return False
    return True


def get_cluster_ingress_ip():
    platform_status = Infrastructure(name="cluster").instance.status.platformStatus
    return platform_status[platform_status["type"].lower()]["ingressIP"]


def extract_addresses(config):
    return [{"ip": address["ip"], PREFIX_LENGTH: address[PREFIX_LENGTH]} for address in config]


def assert_config_unchanged(default_state, bridge_state):
    routes = "routes"
    config_failures = []
    config_to_compare = [
        IPV4_ADDRESSES,
        IPV6_ADDRESSES,
        "dns-resolver",
        routes,
    ]
    LOGGER.info(f"Comparing {default_state['node'].name} state before and after bridge deployment")
    for key in config_to_compare:
        if default_state[key] != bridge_state[key]:
            if key == routes and valid_routes(default_routes=default_state[key], bridge_routes=bridge_state[key]):
                continue

            if key in [IPV6_ADDRESSES, IPV4_ADDRESSES] and valid_addresses(
                default_addresses=default_state[key],
                bridge_addresses=bridge_state[key],
                ip_family=key,
            ):
                continue

            config_failures.append(
                f"{key} config mismatch. Previous state - {default_state[key]}. Current state - {bridge_state[key]}"
            )

    assert not config_failures, config_failures


def collect_primary_interface_state(node):
    nns = NodeNetworkState(name=node.name)

    primary_interface = next(
        route["next-hop-interface"] for route in nns.routes["running"] if "0.0.0.0/0" in route["destination"]
    )
    config = next(interface for interface in nns.interfaces if primary_interface in interface["name"])
    ipv4_config = config[IPV4_STR]
    ipv6_config = config[IPV6_STR]
    ipv4_addresses = extract_addresses(config=ipv4_config["address"])
    ipv6_addresses = extract_addresses(config=ipv6_config["address"])
    dns_resolver = {"config": {"server": nns.instance.status.currentState["dns-resolver"]["running"]["server"]}}
    routes = []
    for route in nns.routes["running"]:
        if primary_interface in route["next-hop-interface"]:
            route = dict(route)
            del route["table-id"]
            routes.append(route)

    return {
        "node": node,
        "primary_interface": primary_interface,
        "ipv4_config": ipv4_config,
        "ipv6_config": ipv6_config,
        IPV4_ADDRESSES: ipv4_addresses,
        IPV6_ADDRESSES: ipv6_addresses,
        "dns-resolver": dns_resolver,
        "routes": {"config": routes},
    }


def static_primary_interface(worker_node):
    iface_state = collect_primary_interface_state(node=worker_node)
    if iface_state["ipv4_config"]["dhcp"]:
        LOGGER.info(f"Setting {worker_node.name}'s default iface to static config")

        with EthernetNetworkConfigurationPolicy(
            name=f"static-ip-{worker_node.name}",
            node_selector=get_node_selector_dict(node_selector=worker_node.name),
            ipv4_dhcp=False,
            ipv4_enable=True,
            ipv6_enable=True,
            ipv6_dhcp=False,
            ipv4_addresses=iface_state["ipv4_addresses"],
            ipv6_addresses=iface_state["ipv6_addresses"],
            routes=iface_state["routes"],
            dns_resolver=iface_state["dns-resolver"],
            interfaces_name=[iface_state["primary_interface"]],
            teardown_absent_ifaces=False,
            success_timeout=TIMEOUT_9MIN,
        ):
            yield collect_primary_interface_state(node=worker_node)

        ipv4_config = iface_state["ipv4_config"]
        ipv6_config = iface_state["ipv6_config"]

        with EthernetNetworkConfigurationPolicy(
            name=f"dynamic-ip-{worker_node.name}",
            node_selector=get_node_selector_dict(node_selector=worker_node.name),
            ipv4_dhcp=ipv4_config["dhcp"],
            ipv4_auto_dns=ipv4_config["auto-dns"],
            ipv4_enable=ipv4_config["enabled"],
            ipv6_enable=ipv6_config["enabled"],
            ipv6_dhcp=ipv6_config["dhcp"],
            ipv6_auto_dns=ipv6_config["auto-dns"],
            interfaces_name=[iface_state["primary_interface"]],
            dns_resolver={"config": {"server": []}},
            teardown_absent_ifaces=False,
        ):
            LOGGER.info(f"{worker_node.name} - Reverting to previous state")

    else:
        LOGGER.info(f"{worker_node.name}'s default iface is already using static config, no need to modify")
        yield iface_state


@pytest.fixture(scope="class")
def label_capture_nodes(worker_node1, worker_node2):
    yield from label_nodes(nodes=[worker_node1, worker_node2], labels=NODE_LABEL)


@pytest.fixture(scope="class")
def static_primary_interface_worker_1(label_capture_nodes, worker_node1):
    yield from static_primary_interface(worker_node=worker_node1)


@pytest.fixture(scope="class")
def static_primary_interface_worker_2(label_capture_nodes, worker_node2):
    yield from static_primary_interface(worker_node=worker_node2)


@pytest.fixture(scope="class")
def capture_bridge(
    static_primary_interface_worker_1,
    static_primary_interface_worker_2,
    label_capture_nodes,
):
    br_name = "capture-br1"
    routes_running_next_hop = "routes.running.next-hop-interface"
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name=f"{br_name}-deployment",
        bridge_name=br_name,
        capture={
            "default-gw": 'routes.running.destination=="0.0.0.0/0"',
            PRIMARY_NIC: "interfaces.name==capture.default-gw.routes.running.0.next-hop-interface",
            f"{PRIMARY_NIC}-routes": f"{routes_running_next_hop}==capture.primary-nic.interfaces.0.name",
            "default-gw-routes-takeover": (f'capture.{PRIMARY_NIC}-routes | {routes_running_next_hop} := "{br_name}"'),
        },
        ports=["{{ capture.primary-nic.interfaces.0.name }}"],
        routes={"config": "{{ capture.default-gw-routes-takeover.routes.running }}"},
        set_ipv4="{{ capture.primary-nic.interfaces.0.ipv4 }}",
        set_ipv6="{{ capture.primary-nic.interfaces.0.ipv6 }}",
        node_selector_labels=NODE_LABEL,
        teardown_absent_ifaces=False,
    ):
        yield [collect_primary_interface_state(node=node) for node in label_capture_nodes]

    teardown_br = LinuxBridgeNodeNetworkConfigurationPolicy(
        name=f"{br_name}-teardown",
        bridge_name=br_name,
        capture={
            br_name: f'interfaces.name == "{br_name}"',
            f"{br_name}-routes": f'{routes_running_next_hop} == "{br_name}"',
            f"{br_name}-routes-takeover": (
                f"capture.{br_name}-routes | "
                f"{routes_running_next_hop} := capture.{br_name}.interfaces.0.bridge.port.0.name"
            ),
        },
        bridge_state=IFACE_ABSENT_STATE,
        node_selector_labels=NODE_LABEL,
        routes={"config": "{{ capture.capture-br1-routes-takeover.routes.running }}"},
        teardown_absent_ifaces=False,
    )
    teardown_br.add_interface(
        name="{{ capture.capture-br1.interfaces.0.bridge.port.0.name }}",
        type_="ethernet",
        set_ipv4="{{ capture.capture-br1.interfaces.0.ipv4 }}",
        set_ipv6="{{ capture.capture-br1.interfaces.0.ipv6 }}",
        state=IFACE_UP_STATE,
    )
    teardown_br.deploy()
    teardown_br.clean_up()


@pytest.fixture()
def bad_syntax_br(static_primary_interface_worker_1):
    br_name = "bad-br"
    bad_br = LinuxBridgeNodeNetworkConfigurationPolicy(
        name="capture-bridge-bad-syntax",
        bridge_name=br_name,
        capture={
            "default-gw": 'routes.running.destination=="0.0.0.0/0"',
            PRIMARY_NIC: "interfaces.name==capture.default-gw.routes.running.0.next-hop-interface",
            f"{PRIMARY_NIC}-routes": f"routes.running.next-hop-interface==capture.{PRIMARY_NIC}.wrong.0.name",
            "default-gw-routes-takeover": (
                f'capture.{PRIMARY_NIC}-routes | routes.running.next-hop-interface := "{br_name}"'
            ),
        },
        ports=["{{ capture.primary-nic.wrong.0.name }}"],
        routes={"config": "{{ capture.default-gw-routes-takeover.routes.wrong }}"},
        set_ipv4="{{ capture.primary-nic.wrong.0.ipv4 }}",
        set_ipv6="{{ capture.primary-nic.interfaces.0.ipv6 }}",
        teardown=False,
        node_selector=get_node_selector_dict(node_selector=static_primary_interface_worker_1["node"].name),
    )
    yield bad_br
    bad_br.delete()


@pytest.mark.destructive
class TestNmpolicy:
    @pytest.mark.polarion("CNV-7595")
    def test_nmpolicy_configuration_collection(
        self,
        static_primary_interface_worker_1,
        static_primary_interface_worker_2,
        capture_bridge,
    ):
        """Test a single nmpolicy yaml successfully collects configuration for two different nodes"""

        for config in (
            static_primary_interface_worker_1,
            static_primary_interface_worker_2,
        ):
            assert_config_unchanged(
                default_state=config,
                bridge_state=[node for node in capture_bridge if node["node"] == config["node"]][0],
            )

    @pytest.mark.xfail()
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7740")
    def test_nmpolicy_connectivity_ipv4(self, capture_bridge):
        """Test bridge deployment behind default interface doesn't affect node connectivity"""
        unreachable_nodes = []
        for node in capture_bridge:
            node_ip = node["ipv4_addresses"][0]["ip"]
            if not subprocess.check_output(["ping", "-c", "1", node_ip]):
                unreachable_nodes.append(node["node"].name)

        assert not unreachable_nodes, f"{unreachable_nodes} unreachable after capture br deployment"


@pytest.mark.polarion("CNV-7741")
def test_nmpolicy_wrong_syntax(bad_syntax_br):
    """Test nmpolicy doesn't allow applying yamls with wrong syntax"""

    with pytest.raises((NNCPConfigurationFailed, TimeoutExpiredError)):
        bad_syntax_br.deploy()
