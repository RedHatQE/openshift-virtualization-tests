"""
VM to VM connectivity over bridge with custom MTU (jumbo frame)
"""

from collections import OrderedDict

import pytest

from tests.network.utils import assert_no_ping
from utilities.infra import get_node_selector_dict
from utilities.network import (
    assert_ping_successful,
    cloud_init_network_data,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [
    pytest.mark.usefixtures(
        "hyperconverged_ovs_annotations_enabled_scope_session",
    ),
]


@pytest.fixture(scope="class")
def jumbo_frame_bridge_device_name(index_number):
    yield f"br{next(index_number)}test"


@pytest.fixture(scope="class")
def jumbo_frame_bridge_device_worker_1(
    cluster_hardware_mtu,
    bridge_device_matrix__class__,
    worker_node1,
    nodes_available_nics,
    jumbo_frame_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="jumbo-frame-bridge-nncp-1",
        interface_name=jumbo_frame_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
        mtu=cluster_hardware_mtu,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def jumbo_frame_bridge_device_worker_2(
    cluster_hardware_mtu,
    bridge_device_matrix__class__,
    worker_node2,
    nodes_available_nics,
    jumbo_frame_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name="jumbo-frame-bridge-nncp-2",
        interface_name=jumbo_frame_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
        mtu=cluster_hardware_mtu,
    ) as br:
        yield br


@pytest.fixture(scope="class")
def br1test_bridge_nad(
    cluster_hardware_mtu,
    bridge_device_matrix__class__,
    namespace,
    jumbo_frame_bridge_device_name,
    jumbo_frame_bridge_device_worker_1,
    jumbo_frame_bridge_device_worker_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{jumbo_frame_bridge_device_name}-nad",
        interface_name=jumbo_frame_bridge_device_name,
        mtu=cluster_hardware_mtu,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def bridge_attached_vma(worker_node1, namespace, unprivileged_client, br1test_bridge_nad):
    name = "vma"
    networks = OrderedDict()
    networks[br1test_bridge_nad.name] = br1test_bridge_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture(scope="class")
def bridge_attached_vmb(worker_node2, namespace, unprivileged_client, br1test_bridge_nad):
    name = "vmb"
    networks = OrderedDict()
    networks[br1test_bridge_nad.name] = br1test_bridge_nad.name
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.2/24"]}}}
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
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


class TestJumboFrameBridge:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-2685")
    def test_connectivity_over_linux_bridge_large_mtu(
        self,
        namespace,
        br1test_bridge_nad,
        bridge_attached_vma,
        bridge_attached_vmb,
    ):
        """
        Check connectivity over linux bridge with custom MTU
        """
        icmp_header = 8
        ip_header = 20
        assert_ping_successful(
            src_vm=bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(vm=bridge_attached_vmb, name=br1test_bridge_nad.name),
            packet_size=br1test_bridge_nad.mtu - ip_header - icmp_header,
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3788")
    def test_negative_mtu_linux_bridge(
        self,
        namespace,
        br1test_bridge_nad,
        bridge_attached_vma,
        bridge_attached_vmb,
    ):
        """
        Check connectivity failed when packet size is higher than custom MTU
        """
        assert_no_ping(
            src_vm=bridge_attached_vma,
            dst_ip=get_vmi_ip_v4_by_name(vm=bridge_attached_vmb, name=br1test_bridge_nad.name),
            packet_size=br1test_bridge_nad.mtu + 100,
        )
