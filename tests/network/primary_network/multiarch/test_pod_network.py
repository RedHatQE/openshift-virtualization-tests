"""
Multi-architecture VM to VM connectivity over pod network

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs.connectivity import build_ping_command


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
        dst_ip = lookup_iface_status_ip(vm=amd_vm, iface_name="default", ip_family=4)
        ping_cmd = build_ping_command(dst_ip=str(dst_ip), count=10, timeout=10)
        arm_vm.console(commands=[ping_cmd], timeout=20)

    @pytest.mark.polarion("CNV-15969")
    def test_pod_network_connectivity_amd_to_arm(self, arm_vm, amd_vm):
        """
        Test connectivity from VM on AMD architecture to VM on ARM over pod network.

        Steps:
            1. ICMP (ping) from AMD VM to ARM VM

        Expected:
            - 0 packet loss
        """
        dst_ip = lookup_iface_status_ip(vm=arm_vm, iface_name="default", ip_family=4)
        ping_cmd = build_ping_command(dst_ip=str(dst_ip), count=10, timeout=10)
        amd_vm.console(commands=[ping_cmd], timeout=20)
