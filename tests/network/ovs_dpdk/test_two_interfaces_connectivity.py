"""
OVS-DPDK VM with two interfaces connectivity tests.

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest


class TestReachabilityByVlan:
    """
    Tests for a VM with two OVS-DPDK network interfaces, each backed by a separate
    ResourceClaimTemplate-generated claim isolated on its own VLAN, traffic flows independently
    on each interface and does not cross between the two VLANs.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Two ResourceClaimTemplates, each generating a claim for one OVS-DPDK device,
          each claim configured with a different VLAN tag (VLAN-A, VLAN-B)
        - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
        - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
    """

    __test__ = False

    @pytest.mark.manual
    def test_no_connectivity_across_vlans(self):
        """
        [NEGATIVE] Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a
        separate ResourceClaimTemplate-generated claim isolated on its own VLAN, has no cross-VLAN
        TCP connectivity to the reference VM.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Attempt TCP connection from the under-test VM's first OVS-DPDK interface (VLAN-A) to the
               reference VM's second OVS-DPDK interface (VLAN-B)

        Expected:
            - TCP connectivity across the two VLANs (first interface on VLAN-A to VLAN-B) fails
        """

    @pytest.mark.manual
    def test_first_network(self):
        """
        Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a separate
        ResourceClaimTemplate-generated claim isolated on its own VLAN, has TCP connectivity to the
        reference VM over the first OVS-DPDK interface.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Establish TCP connection from the under-test VM to the reference VM over the first OVS-DPDK interface

        Expected:
            - TCP connectivity between the VMs is established over the first OVS-DPDK interface
        """

    @pytest.mark.manual
    def test_second_network(self):
        """
        Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a separate
        ResourceClaimTemplate-generated claim isolated on its own VLAN, has TCP connectivity to the
        reference VM over the second OVS-DPDK interface.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Establish TCP connection from the under-test VM to the reference VM over the second OVS-DPDK interface

        Expected:
            - TCP connectivity between the VMs is established over the second OVS-DPDK interface
        """
