"""
ClusterIP Service connectivity tests

Verify TCP connectivity between VMs through a ClusterIP Kubernetes Service.

Jira: https://redhat.atlassian.net/browse/CNV-89418 # <skip-jira-utils-check>
"""

import pytest

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer, VMTcpClient, is_tcp_connection


@pytest.mark.single_nic
@pytest.mark.polarion("CNV-16277")
def test_tcp_connectivity_via_cluster_ip_service(
    subtests,
    service_server_vm,
    service_client_vm,
    cluster_ip_service_for_server_vm,
):
    """
    Preconditions:
        - Server VM on pod network
        - Client VM on pod network
        - ClusterIP Service exposing the server VM

    Steps:
        1. Start TCP server on the server VM
        2. For each ClusterIP, establish TCP connection from client VM to server VM via the ClusterIP service

    Expected:
        - TCP connection through the ClusterIP service succeeds for all IP families
    """
    for service_ip in cluster_ip_service_for_server_vm.instance.spec.clusterIPs:
        with subtests.test(msg=f"Testing connectivity via {service_ip}"):
            with TcpServer(vm=service_server_vm, port=IPERF_SERVER_PORT) as server:
                with VMTcpClient(
                    vm=service_client_vm,
                    server_ip=service_ip,
                    server_port=IPERF_SERVER_PORT,
                ) as client:
                    assert is_tcp_connection(server=server, client=client), (
                        f"TCP connection from {service_client_vm.name} to {service_server_vm.name} "
                        f"via ClusterIP service {service_ip}:{IPERF_SERVER_PORT} failed"
                    )
