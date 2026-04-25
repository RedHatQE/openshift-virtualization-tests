"""
Multi-architecture network connectivity tests.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/12/changes#top

Markers:
    - multiarch
    - network
"""

import pytest

pytestmark = [pytest.mark.multiarch, pytest.mark.network]


@pytest.mark.polarion("CNV-15942")
def test_udn_connectivity_between_different_archs():
    """
    Test UDN connectivity between VMs on different architectures.

    Preconditions:
        - Multi-architecture cluster with at least one node with AMD64 (x86_64)
          and at least one with ARM64 architectures
        - User Defined Network configured
        - TCP Client VM on AMD64 node
        - TCP Server VM on ARM64 node (different from client)
        - Both VMs connected to the same User Defined Network

    Steps:
        1. Start TCP server on server VM
        2. Establish TCP connection from client VM to server VM using UDN IP address
        3. Verify connectivity

    Expected:
        - TCP connection succeeds
    """


@pytest.mark.polarion("CNV-15943")
def test_services_between_different_archs():
    """
    Test Kubernetes Service connectivity between VMs on different architectures.

    Preconditions:
        - Multi-architecture cluster with at least one node with AMD64 (x86_64)
          and at least one with ARM64 architectures
        - TCP Server VM on ARM64 node
        - TCP Client VM on AMD64 node
        - ClusterIP TCP service exposing the server VM's port

    Steps:
        1. Establish TCP connection from client VM to server VM via the ClusterIP service


    Expected:
        - Successful connectivity with no loss
    """


# Mark tests as unimplemented
test_udn_connectivity_between_different_archs.__test__ = False
test_services_between_different_archs.__test__ = False
