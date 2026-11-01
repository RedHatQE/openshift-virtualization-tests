"""
OVS-DPDK upgrade tests.

TCP connectivity between the under-test VM and the reference VM is verified for the
parametrized IP family.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device

Markers:
    - ovs_dpdk
    - special_infra
    - upgrade
    - ocp_upgrade
    - cnv_upgrade
    - eus_upgrade
"""

import os

import pytest

from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.constants.pytest import DEPENDENCY_SCOPE_SESSION

BEFORE_UPGRADE_OVS_DPDK_TCP_CONNECTIVITY_TEST_ID = (
    f"{os.path.abspath(__file__)}::test_ovs_dpdk_tcp_connectivity_before_upgrade"
)

__test__ = False


@pytest.mark.manual
@pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
@pytest.mark.dependency(name=BEFORE_UPGRADE_OVS_DPDK_TCP_CONNECTIVITY_TEST_ID, scope=DEPENDENCY_SCOPE_SESSION)
def test_ovs_dpdk_tcp_connectivity_before_upgrade():
    """
    Test that TCP connectivity between the under-test VM and the reference VM succeeds before the
    cluster upgrade.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

    Steps:
        1. Establish TCP connectivity from the under-test VM to the reference VM

    Expected:
        - TCP connectivity from the under-test VM to the reference VM succeeds
    """


@pytest.mark.manual
@pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
@pytest.mark.dependency(
    depends=[
        IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        BEFORE_UPGRADE_OVS_DPDK_TCP_CONNECTIVITY_TEST_ID,
    ],
    scope=DEPENDENCY_SCOPE_SESSION,
)
def test_ovs_dpdk_under_test_vm_running_and_tcp_connectivity_after_upgrade():
    """
    Test that the under-test VM remains running after the cluster upgrade and that TCP connectivity
    to the reference VM is re-established.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Cluster upgrade has completed
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

    Steps:
        1. Verify the under-test VM is in Running state
        2. Establish new TCP connectivity from the under-test VM to the reference VM

    Expected:
        - Under-test VM is Running after the cluster upgrade completes
        - TCP connectivity from the under-test VM to the reference VM is re-established after the
          upgrade completes
    """
