import pytest

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.constants import BRCNV
from tests.network.utils import vm_for_brcnv_tests
from utilities.constants import OVS_BRIDGE
from utilities.infra import get_node_selector_dict
from utilities.network import assert_ping_successful, network_nad


@pytest.fixture(scope="module")
def brcnv_ovs_nad_vlan_2(
    admin_client,
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
        client=admin_client,
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
        dst_ip=lookup_iface_status_ip(vm=brcnv_vmc_with_vlans_1_2, iface_name=brcnv_ovs_nad_vlan_1.name, ip_family=4),
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
        dst_ip=lookup_iface_status_ip(vm=brcnv_vmb_with_vlan_1, iface_name=brcnv_ovs_nad_vlan_1.name, ip_family=4),
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
            dst_ip=lookup_iface_status_ip(
                vm=brcnv_vmc_with_vlans_1_2, iface_name=brcnv_ovs_nad_vlan_1.name, ip_family=4
            ),
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
                dst_ip=lookup_iface_status_ip(
                    vm=brcnv_vmc_with_vlans_1_2, iface_name=brcnv_ovs_nad_vlan_2.name, ip_family=4
                ),
            )
