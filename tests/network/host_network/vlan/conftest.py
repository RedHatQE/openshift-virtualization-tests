# -*- coding: utf-8 -*-

import logging
import shlex

import pytest
from ocp_resources.node_network_configuration_policy import (
    NodeNetworkConfigurationPolicy,
)
from pyhelper_utils.shell import run_ssh_commands

from tests.network.host_network.vlan.utils import (
    DHCP_IP_SUBNET,
    dhcp_server_cloud_init_data,
    disable_ipv4_dhcp_client,
    enable_ipv4_dhcp_client,
)
from tests.network.utils import DHCP_SERVICE_RESTART
from utilities.constants import LINUX_BRIDGE, NODE_TYPE_WORKER_LABEL
from utilities.infra import get_node_selector_dict, get_node_selector_name
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    VLANInterfaceNodeNetworkConfigurationPolicy,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures("workers_type")


@pytest.fixture(scope="module")
def vlan_index_number_for_all_nodes(vlan_index_number):
    return next(vlan_index_number)


# VLAN on interface fixtures
@pytest.fixture(scope="class")
def vlan_iface_dhcp_client_1(
    vlan_base_iface,
    dhcp_client_1,
    vlan_index_number_for_all_nodes,
):
    nncp_name = "dhcp-vlan-client-1-nncp"
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name=nncp_name,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_index_number_for_all_nodes,
        node_selector=get_node_selector_dict(node_selector=dhcp_client_1.hostname),
        ipv4_enable=True,
        ipv4_dhcp=True,
        ipv6_enable=False,
        teardown=False,
    ) as vlan_iface:
        yield vlan_iface

    vlan_iface = NodeNetworkConfigurationPolicy(name=nncp_name)
    if vlan_iface.exists:
        vlan_iface.clean_up()


@pytest.fixture(scope="class")
def vlan_iface_dhcp_client_2(
    vlan_base_iface,
    dhcp_client_2,
    vlan_index_number_for_all_nodes,
):
    nncp_name = "dhcp-vlan-client-2-nncp"
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name=nncp_name,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_index_number_for_all_nodes,
        node_selector=get_node_selector_dict(node_selector=dhcp_client_2.hostname),
        ipv4_enable=True,
        ipv4_dhcp=True,
        ipv6_enable=False,
        teardown=False,
    ) as vlan_iface:
        yield vlan_iface

    vlan_iface = NodeNetworkConfigurationPolicy(name=nncp_name)
    if vlan_iface.exists:
        vlan_iface.clean_up()


@pytest.fixture(scope="class")
def vlan_iface_on_dhcp_client_2_with_different_tag(
    vlan_base_iface,
    vlan_index_number,
    dhcp_client_nodes,
    dhcp_client_2,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=next(vlan_index_number),
        ipv4_enable=True,
        ipv4_dhcp=True,
        node_selector=get_node_selector_dict(node_selector=dhcp_client_2.hostname),
    ) as vlan_iface:
        yield vlan_iface


@pytest.fixture()
def vlan_iface_on_all_worker_nodes(
    label_schedulable_nodes,
    vlan_base_iface,
    vlan_index_number_for_all_nodes,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_index_number_for_all_nodes,
        node_selector_labels=NODE_TYPE_WORKER_LABEL,
    ) as vlan_iface:
        yield vlan_iface


# DHCP VM fixtures
@pytest.fixture(scope="module")
def dhcp_server(running_dhcp_server_vm):
    """
    Once a VM is up and running - start a DHCP server on it.
    """
    run_ssh_commands(
        host=running_dhcp_server_vm.ssh_exec,
        commands=[shlex.split(DHCP_SERVICE_RESTART)],
    )
    return running_dhcp_server_vm


@pytest.fixture(scope="module")
def dhcp_server_vm(namespace, worker_node1, dhcp_br_nad, unprivileged_client):
    cloud_init_data = dhcp_server_cloud_init_data(dhcp_iface_ip_addr=f"{DHCP_IP_SUBNET}.1")
    vm_name = "dhcp-server-vm"

    networks = [dhcp_br_nad.name]
    interfaces = [dhcp_br_nad.bridge_name]

    # Network name in VM spec is not allowed to contain dots (allowed characters are
    # alphabetical characters, numbers, dashes (-) or underscores (_) ).
    vm_interfaces = [iface.replace(".", "-") for iface in interfaces]
    vm_networks = dict(zip(vm_interfaces, networks))

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=vm_networks,
        interfaces=vm_interfaces,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def running_dhcp_server_vm(dhcp_server_vm):
    return running_vm(vm=dhcp_server_vm, wait_for_cloud_init=True)


@pytest.fixture(scope="module")
def dhcp_server_bridge(dhcp_server_vlan_iface, worker_node1):
    bridge_name = "dhcp-server-br"
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
        ports=[dhcp_server_vlan_iface.iface_name],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as br:
        yield br


@pytest.fixture(scope="module")
def dhcp_br_nad(dhcp_server_bridge, namespace):
    nad_name = f"{dhcp_server_bridge.bridge_name}-nad"

    # Apparently, NetworkAttachmentDefinition name cannot contain dot (although k8s resource naming
    # does allow that - https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names).
    nad_name = nad_name.replace(".", "-")
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=nad_name,
        interface_name=dhcp_server_bridge.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def dhcp_server_vlan_iface(
    worker_node1,
    vlan_base_iface,
    vlan_index_number_for_all_nodes,
):
    with VLANInterfaceNodeNetworkConfigurationPolicy(
        name="dhcp-server-vlan-nncp",
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        base_iface=vlan_base_iface,
        tag=vlan_index_number_for_all_nodes,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as vlan_iface:
        yield vlan_iface


# DHCP clients fixtures
@pytest.fixture(scope="module")
def dhcp_client_nodes(dhcp_server_vm, workers_utility_pods):
    dhcp_client_nodes = []
    node_selector_name = get_node_selector_name(node_selector=dhcp_server_vm.node_selector)
    for pod in workers_utility_pods:
        """
        Allow all nodes to be DHCP clients, except for the one hosting the DHCP server. The reason for this
        exception is a known limitation, where a VLAN DHCP client interface can't be served by a DHCP
        server, if they both run on the same node.
        """
        if pod.node.name != node_selector_name:
            dhcp_client_nodes.append(pod.node)
    return dhcp_client_nodes


@pytest.fixture(scope="class")
def dhcp_client_1(dhcp_client_nodes):
    return dhcp_client_nodes[0]


@pytest.fixture(scope="class")
def dhcp_client_2(dhcp_client_nodes):
    return dhcp_client_nodes[1]


@pytest.fixture()
def disabled_dhcp_client_2(vlan_iface_dhcp_client_2, dhcp_client_2):
    disable_ipv4_dhcp_client(vlan_iface_nncp=vlan_iface_dhcp_client_2, selected_node=dhcp_client_2.name)
    yield dhcp_client_2
    enable_ipv4_dhcp_client(vlan_iface_nncp=vlan_iface_dhcp_client_2, selected_node=dhcp_client_2.name)


# VLAN on BOND fixtures
@pytest.fixture(scope="class")
def vlan_iface_bond_dhcp_client_1(
    index_number,
    hosts_common_available_ports,
    dhcp_client_1,
    vlan_index_number_for_all_nodes,
):
    with BondNodeNetworkConfigurationPolicy(
        name=f"vlan-bond{next(index_number)}-nncp",
        bond_name="bond4vlan",
        bond_ports=hosts_common_available_ports[-2:],
        node_selector=get_node_selector_dict(node_selector=dhcp_client_1.hostname),
    ) as bond_iface:
        with VLANInterfaceNodeNetworkConfigurationPolicy(
            name="dhcp-vlan-bond1",
            iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
            base_iface=bond_iface.bond_name,
            tag=vlan_index_number_for_all_nodes,
            node_selector=get_node_selector_dict(node_selector=dhcp_client_1.hostname),
            ipv4_enable=True,
            ipv4_dhcp=True,
            ipv6_enable=False,
        ) as vlan_iface:
            yield vlan_iface


@pytest.fixture(scope="class")
def vlan_iface_bond_dhcp_client_2(
    index_number,
    hosts_common_available_ports,
    dhcp_client_2,
    vlan_iface_bond_dhcp_client_1,
    vlan_index_number_for_all_nodes,
):
    with BondNodeNetworkConfigurationPolicy(
        name=f"vlan-bond{next(index_number)}-nncp",
        bond_name=vlan_iface_bond_dhcp_client_1.base_iface,
        bond_ports=hosts_common_available_ports[-2:],
        node_selector=get_node_selector_dict(node_selector=dhcp_client_2.hostname),
    ) as bond_iface:
        with VLANInterfaceNodeNetworkConfigurationPolicy(
            name="dhcp-vlan-bond2",
            iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
            base_iface=bond_iface.bond_name,
            tag=vlan_index_number_for_all_nodes,
            node_selector=get_node_selector_dict(node_selector=dhcp_client_2.hostname),
            ipv4_enable=True,
            ipv4_dhcp=True,
            ipv6_enable=False,
        ) as vlan_iface:
            yield vlan_iface
