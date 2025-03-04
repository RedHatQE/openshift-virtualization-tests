"""
VM to VM connectivity over pod network (primary interface) with custom MTU (jumbo frame),
on clusters running OVN Kubernetes CNI.
"""

import pytest

from tests.network.utils import assert_no_ping, get_destination_ip_address
from utilities.network import assert_ping_successful


class TestJumboPodNetworkOnly:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-9660")
    def test_jumbo_traffic_over_pod_network_separate_nodes(
        self,
        running_vma_jumbo_primary_interface_worker_1,
        running_vmb_jumbo_primary_interface_worker_2,
        cluster_network_mtu,
    ):
        assert_ping_successful(
            src_vm=running_vma_jumbo_primary_interface_worker_1,
            packet_size=cluster_network_mtu,
            dst_ip=get_destination_ip_address(destination_vm=running_vmb_jumbo_primary_interface_worker_2),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-9671")
    def test_jumbo_traffic_over_pod_network_same_node(
        self,
        running_vma_jumbo_primary_interface_worker_1,
        running_vmc_jumbo_primary_interface_worker_1,
        cluster_network_mtu,
    ):
        assert_ping_successful(
            src_vm=running_vma_jumbo_primary_interface_worker_1,
            packet_size=cluster_network_mtu,
            dst_ip=get_destination_ip_address(destination_vm=running_vmc_jumbo_primary_interface_worker_1),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-9672")
    def test_jumbo_negative_traffic_over_pod_network_with_oversized_traffic(
        self,
        running_vma_jumbo_primary_interface_worker_1,
        running_vmb_jumbo_primary_interface_worker_2,
        cluster_network_mtu,
    ):
        dst_ip = get_destination_ip_address(destination_vm=running_vmb_jumbo_primary_interface_worker_2)
        assert_no_ping(
            src_vm=running_vma_jumbo_primary_interface_worker_1,
            dst_ip=dst_ip,
            packet_size=cluster_network_mtu + 500,
        )


class TestJumboPodNetworkAndSecondary:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-9663")
    def test_jumbo_traffic_over_pod_network_while_secondary_traffic_flows(
        self,
        running_vmd_jumbo_primary_interface_and_secondary_interface,
        running_vme_jumbo_primary_interface_and_secondary_interface,
        cluster_network_mtu,
        ping_over_secondary,
    ):
        assert_ping_successful(
            src_vm=running_vmd_jumbo_primary_interface_and_secondary_interface,
            packet_size=cluster_network_mtu,
            dst_ip=get_destination_ip_address(
                destination_vm=running_vme_jumbo_primary_interface_and_secondary_interface
            ),
        )
