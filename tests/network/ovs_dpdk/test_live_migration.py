"""
OVS-DPDK network tests.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM

Markers:
    - ovs_dpdk
"""

import pytest


class TestOvsDpdkLiveMigration:
    """
    Tests for live migration of VM with ResourceClaimTemplate-backed OVS-DPDK network devices.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16844")
    @pytest.mark.manual
    def test_connectivity_is_preserved_during_live_migration(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is preserved
        after live migration, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/154

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM

        Steps:
            1. Live-migrate the under-test VM and wait for migration completion
            2. Verify TCP connectivity from the under-test VM to the reference VM

        Expected:
            - TCP connectivity to the reference VM is preserved
        """
