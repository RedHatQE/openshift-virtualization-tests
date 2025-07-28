from collections import OrderedDict

import pytest

from tests.network.constants import BRCNV
from tests.network.utils import vm_for_brcnv_tests
from utilities.constants import OVS_BRIDGE
from utilities.infra import get_node_selector_dict
from utilities.network import (
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_vmi_ip_v4_by_name,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body

OVS_BR = "test-ovs-br"
SEC_IFACE_SUBNET = "10.0.200"
DST_IP_ADDR = SEC_IFACE_SUBNET + ".2"


@pytest.fixture()
def ovs_bridge_on_worker1(worker_node1_pod_executor):
    cmd = "sudo ovs-vsctl"
    worker_node1_pod_executor.exec(command=f"{cmd} add-br {OVS_BR}")
    yield OVS_BR
    worker_node1_pod_executor.exec(command=f"{cmd} del-br {OVS_BR}")


@pytest.fixture()
def ovs_bridge_nad(namespace, ovs_bridge_on_worker1):
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name="ovs-test-nad",
        interface_name=ovs_bridge_on_worker1,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def brcnv_ovs_nad_vlan_2(
    namespace,
    vlan_index_number,
):
    vlan_tag = next(vlan_index_number)
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"{BRCNV}-{vlan_tag}",
        interface_name=BRCNV,
        vlan=vlan_tag,
    ) as nad:
        yield nad


@pytest.fixture()
def brcnv_vmb_with_vlan_1(
    unprivileged_client,
    namespace,
    worker_node1,
    brcnv_ovs_nad_vlan_1,
):
    yield from vm_for_brcnv_tests(
        vm_name="vmb",
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        nads=[brcnv_ovs_nad_vlan_1],
        address_suffix=2,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    )


@pytest.fixture(scope="class")
def brcnv_vmc_with_vlans_1_2(
    unprivileged_client,
    namespace,
    worker_node2,
    brcnv_ovs_nad_vlan_1,
    brcnv_ovs_nad_vlan_2,
):
    yield from vm_for_brcnv_tests(
        vm_name="vmc",
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        nads=[brcnv_ovs_nad_vlan_1, brcnv_ovs_nad_vlan_2],
        address_suffix=3,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
    )


@pytest.fixture()
def vma_with_ovs_based_l2(
    unprivileged_client,
    namespace,
    worker_node1,
    ovs_bridge_on_worker1,
    ovs_bridge_nad,
):
    vm_name = "vm-a-ovs-sec-iface"
    networks = OrderedDict()
    networks[ovs_bridge_nad.name] = ovs_bridge_nad.name
    network_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{SEC_IFACE_SUBNET}.1/24"]},
        }
    }
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def running_vma_with_ovs_based_l2(vma_with_ovs_based_l2):
    vma_with_ovs_based_l2.wait_for_agent_connected()
    return vma_with_ovs_based_l2


@pytest.fixture()
def vmb_with_ovs_based_l2(
    unprivileged_client,
    namespace,
    worker_node1,
    ovs_bridge_on_worker1,
    ovs_bridge_nad,
):
    vm_name = "vm-b-ovs-sec-iface"
    networks = OrderedDict()
    networks[ovs_bridge_nad.name] = ovs_bridge_nad.name
    network_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{DST_IP_ADDR}/24"]},
        }
    }
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def running_vmb_with_ovs_based_l2(vmb_with_ovs_based_l2):
    vmb_with_ovs_based_l2.wait_for_agent_connected()
    return vmb_with_ovs_based_l2


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5636")
@pytest.mark.s390x
def test_ovs_bridge_sanity(
    hyperconverged_ovs_annotations_enabled_scope_session,
    vma_with_ovs_based_l2,
    vmb_with_ovs_based_l2,
    running_vma_with_ovs_based_l2,
    running_vmb_with_ovs_based_l2,
):
    assert_ping_successful(src_vm=running_vma_with_ovs_based_l2, dst_ip=DST_IP_ADDR)


@pytest.mark.ovs_brcnv
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-9038")
def test_vlan_1_over_bridge_with_primary_and_secondary_ifaces(
    brcnv_ovs_nad_vlan_1,
    brcnv_vmb_with_vlan_1,
    brcnv_vmc_with_vlans_1_2,
):
    assert_ping_successful(
        src_vm=brcnv_vmb_with_vlan_1,
        dst_ip=get_vmi_ip_v4_by_name(vm=brcnv_vmc_with_vlans_1_2, name=brcnv_ovs_nad_vlan_1.name),
    )


@pytest.mark.ovs_brcnv
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-8597")
def test_cnv_bridge_vlan_1_connectivity_same_node(
    brcnv_ovs_nad_vlan_1,
    brcnv_vma_with_vlan_1,
    brcnv_vmb_with_vlan_1,
):
    assert_ping_successful(
        src_vm=brcnv_vma_with_vlan_1,
        dst_ip=get_vmi_ip_v4_by_name(vm=brcnv_vmb_with_vlan_1, name=brcnv_ovs_nad_vlan_1.name),
    )


@pytest.mark.ovs_brcnv
class TestBRCNVSeperateNodes:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-8602")
    def test_cnv_bridge_vlan_1_connectivity_different_nodes(
        self,
        brcnv_ovs_nad_vlan_1,
        brcnv_vma_with_vlan_1,
        brcnv_vmc_with_vlans_1_2,
    ):
        assert_ping_successful(
            src_vm=brcnv_vma_with_vlan_1,
            dst_ip=get_vmi_ip_v4_by_name(vm=brcnv_vmc_with_vlans_1_2, name=brcnv_ovs_nad_vlan_1.name),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-8603")
    def test_cnv_bridge_negative_vlans_1_2_connectivity_different_nodes(
        self,
        brcnv_ovs_nad_vlan_2,
        brcnv_vma_with_vlan_1,
        brcnv_vmc_with_vlans_1_2,
    ):
        with pytest.raises(AssertionError):
            assert_ping_successful(
                src_vm=brcnv_vma_with_vlan_1,
                dst_ip=get_vmi_ip_v4_by_name(vm=brcnv_vmc_with_vlans_1_2, name=brcnv_ovs_nad_vlan_2.name),
            )
