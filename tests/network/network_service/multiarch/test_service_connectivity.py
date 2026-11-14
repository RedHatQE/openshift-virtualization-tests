"""
Multi-architecture Kubernetes Service connectivity tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest
from ocp_resources.service import Service

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient, is_tcp_connection
from libs.vm.vm import BaseVirtualMachine


@pytest.mark.multiarch
@pytest.mark.single_nic
@pytest.mark.ipv4
class TestMultiArchService:
    """
    Test Kubernetes Service connectivity between VMs on different architectures.
    Intended to run on any multi-architecture cluster; the arch pair(s) under test
    are discovered at collection time from the worker nodes present in the cluster.

    Preconditions:
        - VM on arch_a worker node
        - VM on arch_b worker node
    """

    @pytest.mark.polarion("CNV-15943")
    def test_services_client_a_to_server_b(
        self,
        arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
        clusterip_service_for_vm_b: Service,
    ):
        """
        Preconditions:
            1. ClusterIP Service exposing vm_b

        Steps:
            1. Establish TCP connection from vm_a (client) to vm_b (server) via ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """
        vm_a, vm_b = arch_pair_vms
        service_ip = clusterip_service_for_vm_b.instance.spec.clusterIP
        with TcpServer(vm=vm_b, port=IPERF_SERVER_PORT) as server:
            with VMTcpClient(vm=vm_a, server_ip=service_ip, server_port=IPERF_SERVER_PORT) as client:
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection from {vm_a.name} to {vm_b.name} "
                    f"via ClusterIP service {service_ip}:{IPERF_SERVER_PORT} failed"
                )

    @pytest.mark.polarion("CNV-16264")
    def test_services_client_b_to_server_a(
        self,
        arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
        clusterip_service_for_vm_a: Service,
    ):
        """
        Preconditions:
            1. ClusterIP Service exposing vm_a

        Steps:
            1. Establish TCP connection from vm_b (client) to vm_a (server) via ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """
        vm_a, vm_b = arch_pair_vms
        service_ip = clusterip_service_for_vm_a.instance.spec.clusterIP
        with TcpServer(vm=vm_a, port=IPERF_SERVER_PORT) as server:
            with VMTcpClient(vm=vm_b, server_ip=service_ip, server_port=IPERF_SERVER_PORT) as client:
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection from {vm_b.name} to {vm_a.name} "
                    f"via ClusterIP service {service_ip}:{IPERF_SERVER_PORT} failed"
                )
