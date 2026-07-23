"""
Multi-architecture VM connectivity over UserDefinedNetwork

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_primary_network


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
    def test_udn_connectivity_amd_client_to_arm_server(self, running_amd_and_arm_vms):
        """
        Test UDN connectivity between VMs on different architectures - client on AMD, server on ARM.

        Steps:
            1. Establish TCP connection from client on AMD VM to server on ARM VM

        Expected:
            - TCP connection succeeds
        """
        amd64_udn_vm, arm64_udn_vm = running_amd_and_arm_vms
        with client_server_active_connection(
            client_vm=amd64_udn_vm,
            server_vm=arm64_udn_vm,
            spec_logical_network=lookup_primary_network(vm=arm64_udn_vm).name,
        ) as (client, server):
            assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-15970")
    def test_udn_connectivity_arm_client_to_amd_server(self, running_amd_and_arm_vms):
        """
        Test UDN connectivity between VMs on different architectures - client on ARM, server on AMD.

        Steps:
            1. Establish TCP connection from client on ARM VM to server on AMD VM

        Expected:
            - TCP connection succeeds
        """
        amd64_udn_vm, arm64_udn_vm = running_amd_and_arm_vms
        with client_server_active_connection(
            client_vm=arm64_udn_vm,
            server_vm=amd64_udn_vm,
            spec_logical_network=lookup_primary_network(vm=amd64_udn_vm).name,
        ) as (client, server):
            assert is_tcp_connection(server=server, client=client)
