"""
OVS-DPDK minor-version upgrade tests.

Preconditions:
    - Running reference VM with a ResourceClaim-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaim-backed OVS-DPDK network device
    - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM

Markers:
    - ovs_dpdk
    - upgrade
    - ocp_upgrade
    - cnv_upgrade
"""

import pytest


class TestOvsDpdkMinorVersionUpgrade:
    """
    Tests for OCP minor-version upgrade with ResourceClaim-backed OVS-DPDK network devices.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4, Polarion: CNV-16864]
            - ipv6 [Markers: ipv6, Polarion: CNV-16865]
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16864")
    @pytest.mark.manual
    def test_running_state_and_tcp_connectivity_after_ocp_minor_version_upgrade(self):
        """
        Test that the under-test VM remains running after an OCP minor-version upgrade and that TCP
        connectivity to the reference VM can be re-established for the parametrized IP family once the
        upgrade completes.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/154

        Preconditions:
            - Running under-test VM with a ResourceClaim-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaim-backed OVS-DPDK network device
            - IPv4+IPv6 TCP connectivity established between the under-test VM and the reference VM

        Steps:
            1. Perform an OCP minor-version upgrade and wait for the upgrade to complete
            2. Verify the under-test VM is still in Running state
            3. Verify TCP connectivity is re-established from the under-test VM to the reference VM
               for the parametrized IP family

        Expected:
            - Under-test VM is Running after the OCP minor-version upgrade completes
            - TCP connectivity from the under-test VM to the reference VM is re-established for the
              parametrized IP family after the upgrade completes
        """
