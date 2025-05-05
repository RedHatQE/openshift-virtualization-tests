# -*- coding: utf-8 -*-

import logging

import pytest

from tests.network.utils import wait_for_address_on_iface
from utilities.constants import LINUX_BRIDGE, NMSTATE_HANDLER
from utilities.infra import get_daemonset_by_name, get_node_pod, get_node_selector_dict, name_prefix
from utilities.network import network_device
from utilities.virt import VirtualMachineForTests, fedora_vm_body

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def worker_nodes_management_iface_stats(nodes_active_nics, worker_node1, worker_node2):
    """
    The fixture create a daictionary containing the host node name and the iface_name:
        node_stats = {
            'n-awax-49-8-v6cnv-worker-0-qsb45': {'iface_name': 'ens3'},
            'n-awax-49-8-v6cnv-worker-0-tgxlk': {'iface_name': 'ens3'}
        }
    """
    node_stats = {}
    for worker in worker_node1, worker_node2:
        node_stats[worker.name] = {"iface_name": nodes_active_nics[worker.name]["occupied"][0]}
    return node_stats


@pytest.fixture(scope="module")
def nmstate_vma(schedulable_nodes, worker_node1, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def nmstate_vmb(schedulable_nodes, worker_node2, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_nmstate_vma(nmstate_vma):
    nmstate_vma.wait_for_agent_connected()
    return nmstate_vma


@pytest.fixture(scope="module")
def running_nmstate_vmb(nmstate_vmb):
    nmstate_vmb.wait_for_agent_connected()
    return nmstate_vmb


@pytest.fixture(scope="module")
def bridge_on_management_ifaces_node1(
    worker_nodes_management_iface_stats,
    worker_node1,
    workers_utility_pods,
):
    # Assuming for now all nodes have the same management interface name
    management_iface = worker_nodes_management_iface_stats[worker_node1.name]["iface_name"]
    worker_pod = get_node_pod(utility_pods=workers_utility_pods, node=worker_node1)
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"brext-default-net-{name_prefix(worker_node1.name)}",
        interface_name="brext1",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[management_iface],
        ipv4_enable=True,
        ipv4_dhcp=True,
    ) as br_dev:
        # Wait for bridge to get management IP
        wait_for_address_on_iface(worker_pod=worker_pod, iface_name=br_dev.bridge_name)
        yield br_dev

    # Verify IP is back to the port
    wait_for_address_on_iface(worker_pod=worker_pod, iface_name=management_iface)


@pytest.fixture(scope="module")
def bridge_on_management_ifaces_node2(
    workers_utility_pods,
    worker_nodes_management_iface_stats,
    worker_node2,
):
    # Assuming for now all nodes has the same management interface name
    management_iface = worker_nodes_management_iface_stats[worker_node2.name]["iface_name"]
    worker_pod = get_node_pod(utility_pods=workers_utility_pods, node=worker_node2)
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"brext-default-net-{name_prefix(worker_node2.name)}",
        interface_name="brext2",
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[management_iface],
        ipv4_enable=True,
        ipv4_dhcp=True,
    ) as br_dev:
        # Wait for bridge to get management IP
        wait_for_address_on_iface(worker_pod=worker_pod, iface_name=br_dev.bridge_name)
        yield br_dev

    # Verify IP is back to the port
    wait_for_address_on_iface(worker_pod=worker_pod, iface_name=management_iface)


@pytest.fixture(scope="module")
def nmstate_ds(admin_client, nmstate_namespace):
    return get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name=NMSTATE_HANDLER,
        namespace_name=nmstate_namespace.name,
    )
