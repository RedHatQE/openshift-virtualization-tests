"""
Create Linux BOND.
Start a VM with bridge on Linux BOND.
"""

from collections import OrderedDict
from contextlib import contextmanager

import pytest

from utilities.constants import TIMEOUT_9MIN
from utilities.infra import ExecCommandOnPod, get_node_selector_dict, get_node_selector_name
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [
    pytest.mark.sno,
    pytest.mark.usefixtures(
        "hyperconverged_ovs_annotations_enabled_scope_session",
        "workers_type",
    ),
]


def assert_bond_validation(utility_pods, bond):
    pod_exec = ExecCommandOnPod(
        utility_pods=utility_pods,
        node=get_node_selector_name(node_selector=bond.node_selector),
    )
    bonding_path = f"/sys/class/net/{bond.bond_name}/bonding"
    mode = pod_exec.exec(command=f"cat {bonding_path}/mode")
    # TODO: rename 'slaves' once file is renamed (offensive language)
    bond_ports = pod_exec.exec(command=f"cat {bonding_path}/slaves")
    worker_bond_ports = bond_ports.split()
    worker_bond_ports.sort()
    bond.bond_ports.sort()
    assert mode.split()[0] == bond.mode
    assert worker_bond_ports == bond.bond_ports


@contextmanager
def create_vm(namespace, nad, node_selector, unprivileged_client):
    name = "bond-vm"
    networks = OrderedDict()
    networks[nad.name] = nad.name

    with VirtualMachineForTests(
        namespace=namespace,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=node_selector,
        client=unprivileged_client,
        ssh=False,
    ) as vm:
        yield vm


@pytest.fixture()
def matrix_bond_modes_bond(
    index_number,
    link_aggregation_mode_no_connectivity_matrix__function__,
    nodes_available_nics,
    worker_node1,
):
    """
    Create BOND if setup support BOND
    """
    bond_index = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"matrix-bond{bond_index}-nncp",
        bond_name=f"mtx-bond{bond_index}",
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        mode=link_aggregation_mode_no_connectivity_matrix__function__,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as bond:
        yield bond


@pytest.fixture()
def bond_modes_nad(bridge_device_matrix__function__, namespace, matrix_bond_modes_bond):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__function__,
        nad_name=f"bond-nad-{matrix_bond_modes_bond.bond_name}",
        interface_name=f"br{matrix_bond_modes_bond.bond_name}",
    ) as nad:
        yield nad


@pytest.fixture()
def matrix_bond_modes_bridge(
    bridge_device_matrix__function__,
    worker_node1,
    bond_modes_nad,
    matrix_bond_modes_bond,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_device(
        interface_type=bridge_device_matrix__function__,
        nncp_name=f"bridge-on-bond-{matrix_bond_modes_bond.bond_name}",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        interface_name=bond_modes_nad.bridge_name,
        ports=[matrix_bond_modes_bond.bond_name],
    ) as br:
        yield br


@pytest.fixture()
def bond_modes_vm(
    worker_node1,
    namespace,
    unprivileged_client,
    bond_modes_nad,
    matrix_bond_modes_bridge,
):
    with create_vm(
        namespace=namespace.name,
        nad=bond_modes_nad,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        unprivileged_client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture()
def bridge_on_bond_fail_over_mac(
    bridge_device_matrix__function__,
    worker_node1,
    bond_modes_nad,
    active_backup_bond_with_fail_over_mac,
):
    """
    Create bridge and attach the BOND to it
    """
    with network_device(
        interface_type=bridge_device_matrix__function__,
        nncp_name="bridge-on-bond-fail-over-mac",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        interface_name=bond_modes_nad.bridge_name,
        ports=[active_backup_bond_with_fail_over_mac.bond_name],
    ) as br:
        yield br


@pytest.fixture()
def active_backup_bond_with_fail_over_mac(index_number, worker_node1, nodes_available_nics):
    bond_index = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"active-bond{bond_index}-nncp",
        bond_name=f"act-bond{bond_index}",
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        options={"fail_over_mac": "active"},
        success_timeout=TIMEOUT_9MIN,
    ) as bond:
        yield bond


@pytest.fixture()
def vm_with_fail_over_mac_bond(
    worker_node1,
    namespace,
    unprivileged_client,
    bond_modes_nad,
    active_backup_bond_with_fail_over_mac,
    bridge_on_bond_fail_over_mac,
):
    with create_vm(
        namespace=namespace.name,
        nad=bond_modes_nad,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        unprivileged_client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture()
def bond_resource(index_number, nodes_available_nics, worker_node1):
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"bond-with-port{bond_idx}nncp",
        bond_name=f"bond-w-port{bond_idx}",
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as bond:
        yield bond


@pytest.mark.polarion("CNV-4382")
def test_bond_created(workers_utility_pods, matrix_bond_modes_bond):
    assert_bond_validation(utility_pods=workers_utility_pods, bond=matrix_bond_modes_bond)


@pytest.mark.polarion("CNV-4383")
def test_vm_started(bond_modes_vm):
    running_vm(vm=bond_modes_vm, check_ssh_connectivity=False, wait_for_interfaces=False)


@pytest.mark.polarion("CNV-6583")
def test_active_backup_bond_with_fail_over_mac(
    index_number,
    worker_node1,
    nodes_available_nics,
    workers_utility_pods,
):
    bond_index = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        name=f"test-active-bond{bond_index}-nncp",
        bond_name=f"test-act-bond{bond_index}",
        bond_ports=nodes_available_nics[worker_node1.name][-2:],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        options={"fail_over_mac": "active"},
    ) as bond:
        assert_bond_validation(utility_pods=workers_utility_pods, bond=bond)


@pytest.mark.polarion("CNV-6584")
def test_vm_bond_with_fail_over_mac_started(
    vm_with_fail_over_mac_bond,
):
    running_vm(
        vm=vm_with_fail_over_mac_bond,
        check_ssh_connectivity=False,
        wait_for_interfaces=False,
    )


@pytest.mark.polarion("CNV-7263")
def test_bond_with_bond_port(workers_utility_pods, bond_resource):
    assert_bond_validation(utility_pods=workers_utility_pods, bond=bond_resource)
