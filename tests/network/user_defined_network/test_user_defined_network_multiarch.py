"""
Multi-architecture VM connectivity over UserDefinedNetwork

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_primary_network
from libs.vm.vm import BaseVirtualMachine


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchUdn:
    """
    Test UDN connectivity between VMs on different architectures.
    Intended to run on any multi-architecture cluster; the arch pair(s) under test
    are discovered at collection time from the worker nodes present in the cluster.

    Preconditions:
        - User Defined Network configured
        - VM on arch_a worker node connected to the UDN
        - VM on arch_b worker node connected to the same UDN
    """

    @pytest.mark.polarion("CNV-15942")
    def test_udn_connectivity_client_a_to_server_b(
        self, arch_pair_udn_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]
    ):
        """
        Test UDN connectivity — client on vm_a, server on vm_b.

        Steps:
            1. Establish TCP connection from vm_a to vm_b over the UDN

        Expected:
            - TCP connection succeeds
        """
        vm_a, vm_b = arch_pair_udn_vms
        with client_server_active_connection(
            client_vm=vm_a,
            server_vm=vm_b,
            spec_logical_network=lookup_primary_network(vm=vm_b).name,
        ) as (client, server):
            assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-15970")
    def test_udn_connectivity_client_b_to_server_a(
        self, arch_pair_udn_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]
    ):
        """
        Test UDN connectivity — client on vm_b, server on vm_a.

        Steps:
            1. Establish TCP connection from vm_b to vm_a over the UDN

        Expected:
            - TCP connection succeeds
        """
        vm_a, vm_b = arch_pair_udn_vms
        with client_server_active_connection(
            client_vm=vm_b,
            server_vm=vm_a,
            spec_logical_network=lookup_primary_network(vm=vm_a).name,
        ) as (client, server):
            assert is_tcp_connection(server=server, client=client)
