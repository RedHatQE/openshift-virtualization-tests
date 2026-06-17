"""
Multi-architecture Kubernetes Service connectivity tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchService:
    """
    Test Kubernetes Service connectivity between VMs on different architectures.
    Intended to run on multi-architecture cluster with AMD64 and ARM64 worker nodes

    Preconditions:
        - VM on ARM64 node
        - VM on AMD64 node
    """

    @pytest.mark.polarion("CNV-15943")
    def test_services_between_amd_client_to_arm_server(self):
        """
        Preconditions:
            1. ClusterIP Service exposing the ARM VM

        Steps:
            1. Establish TCP connection from client on AMD VM to server on ARM VM via the ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """

    @pytest.mark.polarion("CNV-16264")
    def test_services_between_arm_client_to_amd_server(self):
        """
        Preconditions:
            1. ClusterIP Service exposing the AMD VM

        Steps:
            1. Establish TCP connection from client on ARM VM to server on AMD VM via the ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """

    test_services_between_amd_client_to_arm_server.__test__ = False
    test_services_between_arm_client_to_amd_server.__test__ = False
