"""
Multi-architecture VM to VM connectivity over pod network

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from libs.vm.vm import BaseVirtualMachine
from tests.network.primary_network.multiarch.libmultiarch import ping_between_vms


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchPodNetwork:
    """
    Test connectivity between VMs on two different architectures over pod network.
    Intended to run on any multi-architecture cluster; the arch pair(s) under test
    are discovered at collection time from the worker nodes present in the cluster.

    Preconditions:
        - VM on arch_a worker node
        - VM on arch_b worker node
    """

    @pytest.mark.polarion("CNV-15968")
    def test_pod_network_connectivity_a_to_b(self, arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]):
        """
        Test connectivity from vm_a to vm_b over pod network.

        Steps:
            1. ICMP (ping) from vm_a to vm_b

        Expected:
            - 0 packet loss
        """
        vm_a, vm_b = arch_pair_vms
        ping_between_vms(source_vm=vm_a, destination_vm=vm_b)

    @pytest.mark.polarion("CNV-15969")
    def test_pod_network_connectivity_b_to_a(self, arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]):
        """
        Test connectivity from vm_b to vm_a over pod network.

        Steps:
            1. ICMP (ping) from vm_b to vm_a

        Expected:
            - 0 packet loss
        """
        vm_a, vm_b = arch_pair_vms
        ping_between_vms(source_vm=vm_b, destination_vm=vm_a)
