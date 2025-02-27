import logging

import pytest

from tests.network.utils import assert_no_ping
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name

LOGGER = logging.getLogger(__name__)


pytestmark = [
    pytest.mark.usefixtures(
        "enable_multi_network_policy_usage",
    ),
]


class TestFlatOverlayConnectivity:
    @pytest.mark.gating
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10158")
    @pytest.mark.dependency(name="test_flat_overlay_basic_ping")
    def test_flat_overlay_basic_ping(self, flat_overlay_vma_vmb_nad, vma_flat_overlay, vmb_flat_overlay):
        assert_ping_successful(
            src_vm=vma_flat_overlay,
            dst_ip=get_vmi_ip_v4_by_name(vm=vmb_flat_overlay, name=flat_overlay_vma_vmb_nad.name),
        )

    @pytest.mark.polarion("CNV-10159")
    @pytest.mark.dependency(name="test_flat_overlay_separate_nads", depends=["test_flat_overlay_basic_ping"])
    def test_flat_overlay_separate_nads(
        self,
        vma_flat_overlay,
        vmc_flat_overlay,
        vmb_flat_overlay_ip_address,
        vmd_flat_overlay_ip_address,
    ):
        # This ping is needed even though it was tested in test_flat_overlay_basic_ping because an additional network
        # (flat_overlay_vmc_vmd_nad) is now created. We want to make sure that the connectivity wasn't harmed by this
        # addition.
        assert_ping_successful(
            src_vm=vma_flat_overlay,
            dst_ip=vmb_flat_overlay_ip_address,
        )
        assert_ping_successful(
            src_vm=vmc_flat_overlay,
            dst_ip=vmd_flat_overlay_ip_address,
        )

    @pytest.mark.polarion("CNV-10160")
    def test_flat_overlay_separate_nads_no_connectivity(
        self,
        vma_flat_overlay,
        vmd_flat_overlay_ip_address,
    ):
        assert_no_ping(
            src_vm=vma_flat_overlay,
            dst_ip=vmd_flat_overlay_ip_address,
        )

    @pytest.mark.polarion("CNV-10172")
    def test_flat_overlay_connectivity_between_namespaces(
        self,
        flat_overlay_vma_vmb_nad,
        flat_overlay_vme_nad,
        vma_flat_overlay,
        vme_flat_overlay,
    ):
        assert flat_overlay_vma_vmb_nad.name == flat_overlay_vme_nad.name, (
            f"NAD names are not identical:\n first NAD's "
            f"name: {flat_overlay_vma_vmb_nad.name}, second NAD's name: "
            f"{flat_overlay_vme_nad.name}"
        )
        assert_ping_successful(
            src_vm=vma_flat_overlay,
            dst_ip=get_vmi_ip_v4_by_name(vm=vme_flat_overlay, name=flat_overlay_vma_vmb_nad.name),
        )

    @pytest.mark.polarion("CNV-10173")
    def test_flat_overlay_consistent_ip(
        self,
        vmc_flat_overlay_ip_address,
        vmd_flat_overlay,
        ping_before_migration,
        migrated_vmc_flat_overlay,
    ):
        assert_ping_successful(
            src_vm=vmd_flat_overlay,
            dst_ip=vmc_flat_overlay_ip_address,
        )


class TestFlatOverlayJumboConnectivity:
    @pytest.mark.polarion("CNV-10162")
    def test_flat_l2_jumbo_frame_connectivity(
        self,
        flat_l2_jumbo_frame_packet_size,
        flat_overlay_jumbo_frame_nad,
        vma_jumbo_flat_l2,
        vmb_jumbo_flat_l2,
    ):
        assert_ping_successful(
            src_vm=vma_jumbo_flat_l2,
            packet_size=flat_l2_jumbo_frame_packet_size,
            dst_ip=get_vmi_ip_v4_by_name(vm=vmb_jumbo_flat_l2, name=flat_overlay_jumbo_frame_nad.name),
        )
