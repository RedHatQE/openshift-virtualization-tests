"""
Test VLAN network interfaces on hosts network only (not on CNV VM).
"""

import logging

import pytest

from tests.network.host_network.vlan.utils import (
    assert_vlan_dynamic_ip,
    assert_vlan_iface_no_ip,
    assert_vlan_interface,
)
from utilities.infra import ExecCommandOnPod

LOGGER = logging.getLogger(__name__)


class TestVlanInterface:
    @pytest.mark.polarion("CNV-4161")
    def test_vlan_interface_on_all_worker_nodes(
        self,
        schedulable_nodes,
        workers_utility_pods,
        namespace,
        vlan_iface_on_all_worker_nodes,
    ):
        assert_vlan_interface(
            utility_pods=workers_utility_pods,
            iface_name=vlan_iface_on_all_worker_nodes.iface_name,
            schedulable_nodes=schedulable_nodes,
        )

    @pytest.mark.order(before="test_vlan_deletion")
    @pytest.mark.polarion("CNV-3451")
    def test_vlan_connectivity_on_several_hosts(
        self,
        workers_utility_pods,
        namespace,
        vlan_iface_dhcp_client_1,
        vlan_iface_dhcp_client_2,
        dhcp_server,
        dhcp_client_nodes,
    ):
        """
        Test that VLAN NICs on all hosts except for the DHCP server host are assigned a dynamic IP address.
        """
        assert_vlan_dynamic_ip(
            iface_name=vlan_iface_dhcp_client_1.iface_name,
            utility_pods=workers_utility_pods,
            dhcp_clients_list=dhcp_client_nodes,
        )

    @pytest.mark.order(before="test_vlan_deletion")
    @pytest.mark.polarion("CNV-3452")
    def test_vlan_connectivity_on_one_host(
        self,
        workers_utility_pods,
        namespace,
        vlan_iface_dhcp_client_2,
        dhcp_server,
        disabled_dhcp_client_2,
    ):
        """
        Test that VLAN NIC on only one host (which is not the DHCP server host) is assigned a dynamic IP address.
        """
        assert_vlan_iface_no_ip(
            utility_pods=workers_utility_pods,
            iface_name=vlan_iface_dhcp_client_2.iface_name,
            no_dhcp_client_list=[disabled_dhcp_client_2],
        )

    @pytest.mark.order(before="test_vlan_deletion")
    @pytest.mark.polarion("CNV-3463")
    def test_no_connectivity_between_different_vlan_tags(
        self,
        workers_utility_pods,
        namespace,
        dhcp_server,
        dhcp_client_2,
        vlan_iface_on_dhcp_client_2_with_different_tag,
    ):
        """
        Negative: Test that VLAN NICs (that are created using k8s-nmstate) with different tags have no connectivity
        between them.
        """
        assert_vlan_iface_no_ip(
            utility_pods=workers_utility_pods,
            iface_name=vlan_iface_on_dhcp_client_2_with_different_tag.iface_name,
            no_dhcp_client_list=[dhcp_client_2],
        )

    @pytest.mark.polarion("CNV-3462")
    def test_vlan_deletion(
        self,
        workers_utility_pods,
        namespace,
        dhcp_client_nodes,
        vlan_iface_dhcp_client_1,
        vlan_iface_dhcp_client_2,
    ):
        """
        Test that VLAN NICs that are created using k8s-nmstate can be successfully deleted.
        """
        vlan_iface_dhcp_client_1.clean_up()
        vlan_iface_dhcp_client_2.clean_up()
        vlan_iface_name = vlan_iface_dhcp_client_1.iface_name
        for pod in workers_utility_pods:
            if pod.node not in [node.name for node in dhcp_client_nodes]:
                # Exclude the node that run the DHCP server VM
                continue

            pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=pod.node)
            ip_addr_out = pod_exec.exec(command=f"ip addr show {vlan_iface_name} |  wc -l")
            assert int(ip_addr_out.strip()) == 0, (
                f"VLAN interface {vlan_iface_name} was not deleted from node {pod.node.name}."
            )


class TestVlanBond:
    @pytest.mark.polarion("CNV-3469")
    def test_vlan_connectivity_over_bond_on_all_hosts(
        self,
        workers_utility_pods,
        namespace,
        vlan_iface_bond_dhcp_client_1,
        vlan_iface_bond_dhcp_client_2,
        dhcp_server,
        dhcp_client_nodes,
    ):
        """
        Test that VLAN NICs which are configured over bond interfaces, on all hosts except for the DHCP server host
        are assigned a dynamic IP address.
        """
        assert_vlan_dynamic_ip(
            iface_name=vlan_iface_bond_dhcp_client_1.iface_name,
            utility_pods=workers_utility_pods,
            dhcp_clients_list=dhcp_client_nodes,
        )


"""
This test must remain the last one, otherwise there will be no complete tear-down for this module,
and resources will remain hanging.
All tests marked with @pytest.mark.order(before="test_vlan_deletion") to ensure it.
"""
