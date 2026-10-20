"""
OVS-DPDK live migration tests.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest

__test__ = False


@pytest.mark.manual
def test_connectivity_is_preserved_during_live_migration():
    """
    Test that TCP connectivity from the under-test VM to the reference VM is preserved
    during live migration, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

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
