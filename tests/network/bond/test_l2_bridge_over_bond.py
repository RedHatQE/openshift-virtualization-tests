"""
Connectivity over bond bridge on secondary interface
"""

from collections import OrderedDict

import pytest

import utilities.network
from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs import cloudinit as netcloud
from tests.network.libs.ip import random_ipv4_address
from utilities.infra import get_node_selector_dict
from utilities.network import (
    BondNodeNetworkConfigurationPolicy,
    assert_ping_successful,
    cloud_init_network_data,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body

pytestmark = pytest.mark.usefixtures(
    "hyperconverged_ovs_annotations_enabled_scope_session",
    "workers_type",
)


@pytest.fixture(scope="class")
def ovs_linux_br1bond_nad(admin_client, bridge_device_matrix__class__, namespace):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name="br1bond-nad",
        interface_name="br1bond",
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_1(
    admin_client,
    index_number,
    worker_node1,
    hosts_common_available_ports,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    with BondNodeNetworkConfigurationPolicy(
        client=admin_client,
        name=f"bond{bond_idx}nncp-worker-1",
        bond_name=f"bond{bond_idx}",
        bond_ports=hosts_common_available_ports[-2:],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def ovs_linux_bond1_worker_2(
    admin_client,
    index_number,
    worker_node2,
    hosts_common_available_ports,
    ovs_linux_bond1_worker_1,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    with (
        BondNodeNetworkConfigurationPolicy(
            name=f"bond{bond_idx}nncp-worker-2",
            client=admin_client,
            bond_name=ovs_linux_bond1_worker_1.bond_name,  # Use the same BOND name for each test.
            bond_ports=hosts_common_available_ports[-2:],
            node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ) as bond
    ):
        yield bond


@pytest.fixture(scope="class")
def ovs_linux_bridge_on_bond_worker_1(
    admin_client,
    bridge_device_matrix__class__,
    worker_node1,
    ovs_linux_br1bond_nad,
    ovs_linux_bond1_worker_1,
):
    """
    Create bridge and attach the BOND to it
    """
    with utilities.network.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-1",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[ovs_linux_bond1_worker_1.bond_name],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def ovs_linux_bridge_on_bond_worker_2(
    admin_client,
    bridge_device_matrix__class__,
    worker_node2,
    ovs_linux_br1bond_nad,
    ovs_linux_bond1_worker_2,
):
    """
    Create bridge and attach the BOND to it
    """
    with utilities.network.network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="bridge-on-bond-worker-2",
        interface_name=ovs_linux_br1bond_nad.bridge_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[ovs_linux_bond1_worker_2.bond_name],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    ovs_linux_br1bond_nad,
    ovs_linux_bridge_on_bond_worker_1,
):
    name = "bond-vma"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    netdata = netcloud.NetworkData(
        ethernets={"eth1": netcloud.EthernetDevice(addresses=[f"{random_ipv4_address(net_seed=0, host_address=1)}/24"])}
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=netcloud.cloudinit(netdata=netdata),
        client=unprivileged_client,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    ovs_linux_br1bond_nad,
    ovs_linux_bridge_on_bond_worker_2,
):
    name = "bond-vmb"
    networks = OrderedDict()
    networks[ovs_linux_br1bond_nad.name] = ovs_linux_br1bond_nad.name
    network_data_data = {
        "ethernets": {"eth1": {"addresses": [f"{random_ipv4_address(net_seed=0, host_address=2)}/24"]}}
    }
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def ovs_linux_bond_bridge_attached_vms(ovs_linux_bond_bridge_attached_vma, ovs_linux_bond_bridge_attached_vmb):
    vms = (ovs_linux_bond_bridge_attached_vma, ovs_linux_bond_bridge_attached_vmb)
    for vm in vms:
        vm.wait_for_ready_status(status=True)
        vm.wait_for_agent_connected()
    yield vms


class TestBondConnectivity:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3366")
    @pytest.mark.s390x
    def test_bond(
        self,
        namespace,
        ovs_linux_br1bond_nad,
        ovs_linux_bridge_on_bond_worker_1,
        ovs_linux_bridge_on_bond_worker_2,
        ovs_linux_bond_bridge_attached_vms,
    ):
        src_vm, dst_vm = ovs_linux_bond_bridge_attached_vms
        assert_ping_successful(
            src_vm=src_vm,
            dst_ip=lookup_iface_status_ip(
                vm=dst_vm,
                iface_name=ovs_linux_br1bond_nad.name,
                ip_family=4,
            ),
        )
