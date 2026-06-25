"""
Multi-architecture VM to VM connectivity over pod network

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from tests.network.primary_network.multiarch.libmultiarch import ping_between_vms


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchPodNetwork:
    """
    Test connectivity between VM on ARM architecture and VM on AMD over pod network.
    Intended to run on multi-architecture cluster with AMD64 and ARM64 worker nodes.

    Preconditions:
        - VM on ARM64 node
        - VM on AMD64 node
    """

    @pytest.mark.polarion("CNV-15968")
    def test_pod_network_connectivity_arm_to_amd(self, arm_vm, amd_vm):
        """
        Test connectivity from VM on ARM architecture to VM on AMD over pod network.

        Steps:
            1. ICMP (ping) from ARM VM to AMD VM

        Expected:
            - 0 packet loss
        """
        ping_between_vms(source_vm=arm_vm, destination_vm=amd_vm)

    @pytest.mark.polarion("CNV-15969")
    def test_pod_network_connectivity_amd_to_arm(self, arm_vm, amd_vm):
        """
        Test connectivity from VM on AMD architecture to VM on ARM over pod network.

        Steps:
            1. ICMP (ping) from AMD VM to ARM VM

        Expected:
            - 0 packet loss
        """
        ping_between_vms(source_vm=amd_vm, destination_vm=arm_vm)
