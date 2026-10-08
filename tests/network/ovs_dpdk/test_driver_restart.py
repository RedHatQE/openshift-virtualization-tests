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


class TestConnectivityAfterDpdkBackingDriverRestart:
    """
    Tests for OVS-DPDK backing driver restart: existing VM remains reachable, new VM achieves
    connectivity, and the under-test VM remains reachable after live migration, after
    the driver is restarted.

    Preconditions:
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - OVS-DPDK backing driver restart completed and driver is operational
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16845")
    @pytest.mark.manual
    def test_connectivity_existing_vm(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is preserved after
        the OVS-DPDK backing driver is restarted, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/154

        Parametrize:
            - ip_family:
                - ipv4 [Markers: ipv4]
                - ipv6 [Markers: ipv6]

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM
            - OVS-DPDK backing driver restart completed and driver is operational

        Steps:
            1. Verify TCP connectivity from the under-test VM to the reference VM

        Expected:
            - TCP connectivity to the reference VM is preserved
        """

    @pytest.mark.polarion("CNV-16846")
    @pytest.mark.manual
    def test_connectivity_new_vm(self):
        """
        Test that a newly created VM with a ResourceClaim-backed OVS-DPDK network device achieves
        TCP connectivity to the reference VM after the backing driver was restarted, for the
        parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/154

        Parametrize:
            - ip_family:
                - ipv4 [Markers: ipv4]
                - ipv6 [Markers: ipv6]

        Preconditions:
            - OVS-DPDK backing driver restart completed and driver is operational
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

        Steps:
            1. Create and start a VM with a ResourceClaim-backed OVS-DPDK network device
            2. Verify TCP connectivity from the new VM to the reference VM

        Expected:
            - TCP connectivity to the reference VM is preserved
        """

    @pytest.mark.polarion("CNV-16848")
    @pytest.mark.manual
    def test_connectivity_after_driver_restart_and_migration(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is
        preserved after the backing driver was restarted and the under-test VM live-migrated,
        for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/154

        Parametrize:
            - ip_family:
                - ipv4 [Markers: ipv4]
                - ipv6 [Markers: ipv6]

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM
            - OVS-DPDK backing driver restarted and driver is operational

        Steps:
            1. Live-migrate the under-test VM and wait for migration completion
            2. Verify TCP connectivity is preserved from the under-test VM to the reference VM

        Expected:
            - TCP connectivity to the reference VM is preserved
        """
