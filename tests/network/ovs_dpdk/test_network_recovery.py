"""
OVS-DPDK network recovery tests: backing driver restart, guest reboot and OVS restart.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - IPv4+IPv6 TCP connectivity works successfully between the under-test VM and the reference VM

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest


class TestConnectivityAfterDpdkBackingDriverRestart:
    """
    Tests for OVS-DPDK backing driver restart: existing VM remains reachable, new VM achieves
    connectivity, and the under-test VM remains reachable during live migration, after
    the driver is restarted on each worker node.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - OVS-DPDK backing driver restart completed on each worker node and driver is operational
    """

    __test__ = False

    @pytest.mark.manual
    def test_connectivity_existing_vm(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is successful after
        the OVS-DPDK backing driver is restarted, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

        Steps:
            1. Poll TCP connectivity from the under-test VM to the reference VM

        Expected:
            - The new TCP connection to the reference VM is successful
        """

    @pytest.mark.manual
    def test_connectivity_new_vm(self):
        """
        Test that a newly created VM with a ResourceClaim-backed OVS-DPDK network device achieves
        TCP connectivity to the reference VM after the backing driver was restarted, for the
        parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

        Steps:
            1. Create and start a VM with a ResourceClaim-backed OVS-DPDK network device
            2. Poll TCP connectivity from the new VM to the reference VM

        Expected:
            - The new TCP connection to the reference VM is successful
        """

    @pytest.mark.manual
    def test_connectivity_is_preserved_during_live_migration(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is preserved
        during live migration, after the OVS-DPDK backing driver was restarted on each worker
        node, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Active TCP connection established from the under-test VM to the reference VM

        Steps:
            1. Live-migrate the under-test VM and wait for migration completion

        Expected:
            - The active TCP connection from the under-test VM to the reference VM is preserved
              during the migration
        """


@pytest.mark.manual
def test_connectivity_after_guest_reboot():
    """
    Test that TCP connectivity from the under-test VM to the reference VM is successful
    after the under-test VM guest is rebooted, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running under-test VM with a ResourceClaim-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Under-test VM guest is rebooted, running and ready

    Steps:
        1. Establish TCP connection from the under-test VM to the reference VM

    Expected:
        - The new TCP connection to the reference VM is successful
    """


test_connectivity_after_guest_reboot.__test__ = False
