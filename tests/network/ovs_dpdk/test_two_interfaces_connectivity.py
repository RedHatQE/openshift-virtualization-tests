"""
OVS-DPDK VM with two interfaces connectivity tests.

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest

__test__ = False


@pytest.mark.manual
def test_connectivity_over_ovs_dpdk_interfaces():
    """
    Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a separate
    ResourceClaimTemplate-generated claim on a different subnet, has TCP connectivity to the
    reference VM over both interfaces.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running reference VM with two interfaces with separate
          ResourceClaimTemplate-backed OVS-DPDK network devices on two different subnets
        - Running under-test VM with two interfaces with separate
          ResourceClaimTemplate-backed OVS-DPDK network devices on the two subnets as the reference VM

    Steps:
        1. Establish TCP connectivity from the under-test VM to the reference VM over the first OVS-DPDK interface
        2. Establish TCP connectivity from the under-test VM to the reference VM over the second OVS-DPDK interface

    Expected:
        - TCP connectivity from the under-test VM to the reference VM over the first OVS-DPDK interface succeeds
        - TCP connectivity from the under-test VM to the reference VM over the second OVS-DPDK interface succeeds
    """
