"""
Multi-architecture VM connectivity over UserDefinedNetwork

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchUdn:
    """
    Test UDN connectivity between VMs on different architectures.
    Intended to run on multi-architecture cluster with AMD64 and ARM64 worker nodes

    Preconditions:
        - User Defined Network configured
        - VM on AMD64 node
        - VM on ARM64 node
        - Both VMs connected to the same User Defined Network

    """

    @pytest.mark.polarion("CNV-15942")
    def test_udn_connectivity_amd_client_to_arm_server(self):
        """
        Test UDN connectivity between VMs on different architectures - client on AMD, server on ARM.

        Steps:
            1. Establish TCP connection from client on AMD VM to server on ARM VM

        Expected:
            - TCP connection succeeds
        """

    @pytest.mark.polarion("CNV-15970")
    def test_udn_connectivity_arm_client_to_amd_server(self):
        """
        Test UDN connectivity between VMs on different architectures - client on ARM, server on AMD.

        Steps:
            1. Establish TCP connection from client on ARM VM to server on AMD VM

        Expected:
            - TCP connection succeeds
        """

    test_udn_connectivity_arm_client_to_amd_server.__test__ = False
    test_udn_connectivity_amd_client_to_arm_server.__test__ = False
