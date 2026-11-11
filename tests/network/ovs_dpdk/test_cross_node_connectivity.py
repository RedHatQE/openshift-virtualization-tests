"""
OVS-DPDK cross-node VM connectivity tests.

Preconditions:
    - Running server VM with a ResourceClaim-backed OVS-DPDK network device on a worker node

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest

__test__ = False


@pytest.mark.manual
def test_connectivity_between_vms_on_different_nodes():
    """
    Test that two VMs with ResourceClaim-backed OVS-DPDK network devices on different worker
    nodes can establish TCP connectivity, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running server VM with a ResourceClaim-backed OVS-DPDK network device on a worker node, using the
          shared OVS-DPDK device class
        - Running client VM with a ResourceClaim-backed OVS-DPDK network device scheduled on a different
          worker node, using the same OVS-DPDK device class

    Steps:
        1. Verify TCP connectivity between the client RC VM and server RC VM

    Expected:
        - TCP connectivity between the VMs is established
    """
