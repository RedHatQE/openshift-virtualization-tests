"""
Multi-architecture VM to VM connectivity over pod network

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchPodNetwork:
    """
    Test connectivity between VM on ARM architectures and VM on AMD over pod network.
    Intended to run on multi-architecture cluster with AMD64 and ARM64 worker nodes

    Preconditions:
        - VM on ARM64 node
        - VM on AMD64 node
    """

    @pytest.mark.polarion("CNV-15968")
    def test_pod_network_connectivity_arm_to_amd(self):
        """
        Test connectivity from VM on ARM architectures to VM on AMD over pod network.

        Steps:
            1. ICMP (ping) from ARM VM to AMD VM

        Expected:
            - 0 packet loss
        """

    @pytest.mark.polarion("CNV-15969")
    def test_pod_network_connectivity_amd_to_arm(self):
        """
        Test connectivity from VM on AMD architectures to VM on ARM over pod network.

        Steps:
            1. ICMP (ping) from AMD VM to ARM VM

        Expected:
            - 0 packet loss
        """

    test_pod_network_connectivity_arm_to_amd.__test__ = False
    test_pod_network_connectivity_amd_to_arm.__test__ = False
