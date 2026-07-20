"""
Multi-architecture Kubernetes Service connectivity tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md
"""

import pytest

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient, is_tcp_connection


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
    def test_services_between_amd_client_to_arm_server(self, amd_vm, arm_vm, clusterip_service_for_arm_vm):
        """
        Preconditions:
            1. ClusterIP Service exposing the ARM VM

        Steps:
            1. Establish TCP connection from client on AMD VM to server on ARM VM via the ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """
        service_ip = clusterip_service_for_arm_vm.instance.spec.clusterIP
        with TcpServer(vm=arm_vm, port=IPERF_SERVER_PORT) as server:
            with VMTcpClient(vm=amd_vm, server_ip=service_ip, server_port=IPERF_SERVER_PORT) as client:
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection from {amd_vm.name} to {arm_vm.name} "
                    f"via ClusterIP service {service_ip}:{IPERF_SERVER_PORT} failed"
                )

    @pytest.mark.polarion("CNV-16264")
    def test_services_between_arm_client_to_amd_server(self, arm_vm, amd_vm, clusterip_service_for_amd_vm):
        """
        Preconditions:
            1. ClusterIP Service exposing the AMD VM

        Steps:
            1. Establish TCP connection from client on ARM VM to server on AMD VM via the ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """
        service_ip = clusterip_service_for_amd_vm.instance.spec.clusterIP
        with TcpServer(vm=amd_vm, port=IPERF_SERVER_PORT) as server:
            with VMTcpClient(vm=arm_vm, server_ip=service_ip, server_port=IPERF_SERVER_PORT) as client:
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection from {arm_vm.name} to {amd_vm.name} "
                    f"via ClusterIP service {service_ip}:{IPERF_SERVER_PORT} failed"
                )
