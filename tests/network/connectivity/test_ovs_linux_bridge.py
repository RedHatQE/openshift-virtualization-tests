"""
VM to VM connectivity via secondary (bridged) interfaces.
"""

import pytest

from tests.network.connectivity.utils import get_masquerade_vm_ip, is_masquerade
from tests.network.utils import assert_no_ping
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name


class TestConnectivityLinuxBridge:
    @pytest.mark.gating
    @pytest.mark.post_upgrade
    @pytest.mark.parametrize(
        "use_default_bridge",
        [
            pytest.param(
                True,
                marks=pytest.mark.polarion("CNV-11156"),
                id="POD_network",
            ),
            pytest.param(
                False,
                marks=pytest.mark.polarion("CNV-11122"),
                id="L2_bridge_network",
            ),
        ],
    )
    @pytest.mark.ipv4
    def test_ipv4_linux_bridge(
        self,
        use_default_bridge,
        nad_linux_bridge,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        bridge = "default" if use_default_bridge else nad_linux_bridge.name
        assert_ping_successful(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=get_masquerade_vm_ip(
                vm=vm_linux_bridge_attached_vmb_destination,
                ipv6_testing=False,
            )
            if is_masquerade(vm=vm_linux_bridge_attached_vmb_destination, bridge=bridge)
            else get_vmi_ip_v4_by_name(vm=vm_linux_bridge_attached_vmb_destination, name=bridge),
        )

    @pytest.mark.gating
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11125")
    @pytest.mark.ipv6
    def test_ipv6_linux_bridge(
        self,
        skip_if_not_ipv6_supported_cluster,
        nad_linux_bridge,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        bridge = "default"
        assert_ping_successful(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=get_masquerade_vm_ip(
                vm=vm_linux_bridge_attached_vmb_destination,
                ipv6_testing=True,
            )
            if is_masquerade(vm=vm_linux_bridge_attached_vmb_destination, bridge=bridge)
            else get_vmi_ip_v4_by_name(vm=vm_linux_bridge_attached_vmb_destination, name=bridge),
        )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11123")
    @pytest.mark.ipv4
    def test_positive_vlan_linux_bridge(
        self,
        nad_linux_bridge_vlan_1,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        assert_ping_successful(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vm_linux_bridge_attached_vmb_destination,
                name=nad_linux_bridge_vlan_1.name,
            ),
        )

    @pytest.mark.polarion("CNV-11131")
    @pytest.mark.ipv4
    def test_negative_vlan_linux_bridge(
        self,
        nad_linux_bridge_vlan_3,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        assert_no_ping(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vm_linux_bridge_attached_vmb_destination,
                name=nad_linux_bridge_vlan_3.name,
            ),
        )


@pytest.mark.usefixtures("hyperconverged_ovs_annotations_enabled_scope_session")
class TestConnectivityOVSBridge:
    @pytest.mark.gating
    @pytest.mark.post_upgrade
    @pytest.mark.parametrize(
        "use_default_bridge",
        [
            pytest.param(
                True,
                marks=pytest.mark.polarion("CNV-11157"),
                id="POD_network",
            ),
            pytest.param(
                False,
                marks=pytest.mark.polarion("CNV-11126"),
                id="L2_bridge_network",
            ),
        ],
    )
    @pytest.mark.ipv4
    def test_ipv4_ovs_bridge(
        self,
        use_default_bridge,
        nad_ovs_bridge,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        bridge = "default" if use_default_bridge else nad_ovs_bridge.name
        assert_ping_successful(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=get_masquerade_vm_ip(
                vm=vm_ovs_bridge_attached_vmb_destination,
                ipv6_testing=False,
            )
            if is_masquerade(vm=vm_ovs_bridge_attached_vmb_destination, bridge=bridge)
            else get_vmi_ip_v4_by_name(vm=vm_ovs_bridge_attached_vmb_destination, name=bridge),
        )

    @pytest.mark.gating
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11128")
    @pytest.mark.ipv6
    def test_ipv6_ovs_bridge(
        self,
        skip_if_not_ipv6_supported_cluster,
        nad_ovs_bridge,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        bridge = "default"
        assert_ping_successful(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=get_masquerade_vm_ip(
                vm=vm_ovs_bridge_attached_vmb_destination,
                ipv6_testing=True,
            )
            if is_masquerade(vm=vm_ovs_bridge_attached_vmb_destination, bridge=bridge)
            else get_vmi_ip_v4_by_name(vm=vm_ovs_bridge_attached_vmb_destination, name=bridge),
        )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11129")
    @pytest.mark.ipv4
    def test_positive_vlan_ovs_bridge(
        self,
        nad_ovs_bridge_vlan_1,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        assert_ping_successful(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vm_ovs_bridge_attached_vmb_destination,
                name=nad_ovs_bridge_vlan_1.name,
            ),
        )

    @pytest.mark.polarion("CNV-11130")
    @pytest.mark.ipv4
    def test_negative_vlan_ovs_bridge(
        self,
        nad_ovs_bridge_vlan_3,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        assert_no_ping(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vm_ovs_bridge_attached_vmb_destination,
                name=nad_ovs_bridge_vlan_3.name,
            ),
        )
