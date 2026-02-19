"""
VM to VM connectivity via secondary (bridged) interfaces.
"""

import pytest

from libs.net.vmspec import lookup_iface_status, lookup_iface_status_ip
from tests.network.libs.ip import filter_link_local_addresses
from tests.network.utils import assert_no_ping
from utilities.network import assert_ping_successful


class TestConnectivityLinuxBridge:
    @pytest.mark.gating
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11122")
    def test_linux_bridge(
        self,
        subtests,
        nad_linux_bridge,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        """Verify the Linux bridge interface connectivity while the pod network connectivity is preserved"""
        for iface_name in ["default", nad_linux_bridge.name]:
            iface = lookup_iface_status(vm=vm_linux_bridge_attached_vmb_destination, iface_name=iface_name)
            for ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
                with subtests.test(msg=f"Testing interface {iface.name} with IPv{ip.version}", ip=str(ip)):
                    assert_ping_successful(
                        src_vm=vm_linux_bridge_attached_vma_source,
                        dst_ip=ip,
                    )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11123")
    @pytest.mark.ipv4
    @pytest.mark.s390x
    def test_positive_vlan_linux_bridge(
        self,
        nad_linux_bridge_vlan_1,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        assert_ping_successful(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=lookup_iface_status_ip(
                vm=vm_linux_bridge_attached_vmb_destination,
                iface_name=nad_linux_bridge_vlan_1.name,
                ip_family=4,
            ),
        )

    @pytest.mark.polarion("CNV-11131")
    @pytest.mark.ipv4
    @pytest.mark.s390x
    def test_negative_vlan_linux_bridge(
        self,
        nad_linux_bridge_vlan_3,
        vm_linux_bridge_attached_vma_source,
        vm_linux_bridge_attached_vmb_destination,
    ):
        assert_no_ping(
            src_vm=vm_linux_bridge_attached_vma_source,
            dst_ip=lookup_iface_status_ip(
                vm=vm_linux_bridge_attached_vmb_destination,
                iface_name=nad_linux_bridge_vlan_3.name,
                ip_family=4,
            ),
        )


@pytest.mark.usefixtures("hyperconverged_ovs_annotations_enabled_scope_session")
class TestConnectivityOVSBridge:
    @pytest.mark.post_upgrade
    @pytest.mark.gating
    @pytest.mark.polarion("CNV-12556")
    def test_ovs_bridge(
        self,
        subtests,
        nad_ovs_bridge,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        """Verify the OVS bridge interface connectivity while the pod network connectivity is preserved"""
        for iface_name in ["default", nad_ovs_bridge.name]:
            iface = lookup_iface_status(vm=vm_ovs_bridge_attached_vmb_destination, iface_name=iface_name)
            for ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
                with subtests.test(msg=f"Testing interface {iface.name} with IPv{ip.version}", ip=str(ip)):
                    assert_ping_successful(
                        src_vm=vm_ovs_bridge_attached_vma_source,
                        dst_ip=ip,
                    )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-11129")
    @pytest.mark.ipv4
    @pytest.mark.s390x
    def test_positive_vlan_ovs_bridge(
        self,
        nad_ovs_bridge_vlan_1,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        assert_ping_successful(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=lookup_iface_status_ip(
                vm=vm_ovs_bridge_attached_vmb_destination,
                iface_name=nad_ovs_bridge_vlan_1.name,
                ip_family=4,
            ),
        )

    @pytest.mark.polarion("CNV-11130")
    @pytest.mark.ipv4
    @pytest.mark.s390x
    def test_negative_vlan_ovs_bridge(
        self,
        nad_ovs_bridge_vlan_3,
        vm_ovs_bridge_attached_vma_source,
        vm_ovs_bridge_attached_vmb_destination,
    ):
        assert_no_ping(
            src_vm=vm_ovs_bridge_attached_vma_source,
            dst_ip=lookup_iface_status_ip(
                vm=vm_ovs_bridge_attached_vmb_destination,
                iface_name=nad_ovs_bridge_vlan_3.name,
                ip_family=4,
            ),
        )
