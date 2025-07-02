import pytest

from tests.network.utils import assert_no_ping
from utilities.network import assert_ping_successful


@pytest.mark.incremental
class TestMacSpoof:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7264")
    @pytest.mark.s390x
    def test_macspoof_prevent_connectivity(
        self,
        linux_bridge_attached_vma,
        linux_bridge_attached_vmb,
        linux_bridge_attached_running_vma,
        linux_bridge_attached_running_vmb,
        ping_vmb_from_vma,
        vma_interface_spoofed_mac,
        vmb_ip_address,
    ):
        assert_no_ping(src_vm=linux_bridge_attached_vma, dst_ip=vmb_ip_address)

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7265")
    def test_no_macspoof_allow_connectivity(
        self,
        linux_bridge_attached_vma,
        linux_bridge_attached_vmb,
        linux_bridge_attached_running_vma,
        linux_bridge_attached_running_vmb,
        vms_without_mac_spoof,
        vma_interface_spoofed_mac,
        vmb_ip_address,
    ):
        assert_ping_successful(src_vm=linux_bridge_attached_vma, dst_ip=vmb_ip_address)
