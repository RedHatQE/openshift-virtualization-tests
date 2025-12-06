"""
Flat Overlay Network Connectivity Tests
"""

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


@pytest.mark.s390x
class TestFlatOverlayConnectivity:
    """
    Tests for flat overlay network connectivity between VMs.

    Markers:
        - s390x

    Preconditions:
        - Multi-network policy usage enabled
        - Flat overlay Network Attachment Definition created
        - VM-A running and attached to a flat overlay network
        - VM-B running and attached to a flat overlay network
    """

    @pytest.mark.gating
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10158")
    # Not marked as `conformance`; requires NMState
    @pytest.mark.dependency(name="test_flat_overlay_basic_ping")
    def test_flat_overlay_basic_ping(self, flat_overlay_vma_vmb_nad, vma_flat_overlay, vmb_flat_overlay):
        """
        Test that VMs on the same flat overlay network can communicate.

        Markers:
            - gating
            - ipv4

        Steps:
            1. Get IPv4 address of VM-B
            2. Execute ping from VM-A to VM-B

        Expected:
            - Ping succeeds with 0% packet loss
        """
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
        """
        Test that adding a second flat overlay network does not break existing connectivity.

        Preconditions:
            - Second flat overlay NAD created (flat_overlay_vmc_vmd_nad)
            - VM-C running and attached to a second flat overlay network
            - VM-D running and attached to a second flat overlay network

        Steps:
            1. Execute ping from VM-A to VM-B (original network)
            2. Execute ping from VM-C to VM-D (new network)

        Expected:
            - Both ping commands succeed with 0% packet loss
        """
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
        """
        [NEGATIVE] Test that VMs on separate flat overlay networks cannot communicate.

        Preconditions:
            - VM-A attached to the first flat overlay network (NAD-1)
            - VM-D attached to the second flat overlay network (NAD-2)

        Steps:
            1. Execute ping from VM-A to VM-D

        Expected:
            - Ping fails with 100% packet loss
        """
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
        """
        Test that VMs in different namespaces can communicate via same-named NAD.

        Preconditions:
            - NAD with identical name created in namespace-1 and namespace-2
            - VM-A running in namespace-1 attached to the NAD
            - VM-E running in namespace-2 attached to the NAD

        Steps:
            1. Verify NAD names are identical in both namespaces
            2. Execute ping from VM-A to VM-E

        Expected:
            - Ping succeeds with 0% packet loss
        """
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
        """
        Test that VM retains its IP address after live migration.

        Preconditions:
            - VM-C running with a flat overlay network IP address
            - VM-D running on a flat overlay network
            - Ping from VM-D to VM-C succeeded before migration
            - VM-C live migrated to another node

        Steps:
            1. Execute ping from VM-D to VM-C's original IP address

        Expected:
            - Ping succeeds with 0% packet loss
        """
        assert_ping_successful(
            src_vm=vmd_flat_overlay,
            dst_ip=vmc_flat_overlay_ip_address,
        )


class TestFlatOverlayJumboConnectivity:
    """
    Tests for flat overlay network jumbo frame connectivity.

    Preconditions:
        - Flat overlay NAD configured for jumbo frames
        - VM-A running and attached to jumbo frame NAD
        - VM-B running and attached to jumbo frame NAD
    """

    @pytest.mark.polarion("CNV-10162")
    @pytest.mark.s390x
    def test_flat_l2_jumbo_frame_connectivity(
        self,
        flat_l2_jumbo_frame_packet_size,
        flat_overlay_jumbo_frame_nad,
        vma_jumbo_flat_l2,
        vmb_jumbo_flat_l2,
    ):
        """
        Test that VMs can communicate using jumbo frames on a flat overlay network.

        Markers:
            - s390x

        Steps:
            1. Get IPv4 address of VM-B
            2. Execute ping from VM-A to VM-B with jumbo frame packet size

        Expected:
            - Ping succeeds with 0% packet loss
        """
        assert_ping_successful(
            src_vm=vma_jumbo_flat_l2,
            packet_size=flat_l2_jumbo_frame_packet_size,
            dst_ip=get_vmi_ip_v4_by_name(vm=vmb_jumbo_flat_l2, name=flat_overlay_jumbo_frame_nad.name),
        )
