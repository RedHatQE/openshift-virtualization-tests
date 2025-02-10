import logging
from ipaddress import ip_interface

import pytest

from utilities.constants import PUBLIC_DNS_SERVER_IP
from utilities.network import assert_ping_successful

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.skip("Test should be refactor, this test break the node")


@pytest.mark.destructive
@pytest.mark.order(before="TestAfterBridgeTeardown")
class TestWithDhcpOverBridge:
    @pytest.mark.polarion("CNV-3002")
    def test_ping_between_vms_through_brext(
        self,
        worker_nodes_ipv4_false_secondary_nics,
        bridge_on_management_ifaces_node1,
        bridge_on_management_ifaces_node2,
        nmstate_vma,
        nmstate_vmb,
        running_nmstate_vma,
        running_nmstate_vmb,
    ):
        assert_ping_successful(
            src_vm=running_nmstate_vma,
            dst_ip=ip_interface(running_nmstate_vmb.vmi.interfaces[0]["ipAddress"]).ip,
        )

    @pytest.mark.polarion("CNV-3003")
    def test_ping_remote_ip_through_brext(
        self,
        worker_nodes_ipv4_false_secondary_nics,
        bridge_on_management_ifaces_node1,
        bridge_on_management_ifaces_node2,
        nmstate_vma,
        nmstate_vmb,
        running_nmstate_vma,
        running_nmstate_vmb,
    ):
        assert_ping_successful(src_vm=running_nmstate_vma, dst_ip=PUBLIC_DNS_SERVER_IP)


# Test class should be run as last, because it should check connectivity after,
# bridge was created, got dhcp of management and release it back to the port
# The first test marked with @pytest.mark.order(before="TestAfterBridgeTeardown") to ensure it.
@pytest.mark.destructive
class TestAfterBridgeTeardown:
    @pytest.mark.polarion("CNV-3028")
    def test_ping_between_vms_through_main_interface(
        self,
        worker_nodes_ipv4_false_secondary_nics,
        nmstate_vma,
        nmstate_vmb,
        running_nmstate_vma,
        running_nmstate_vmb,
    ):
        assert_ping_successful(
            src_vm=running_nmstate_vma,
            dst_ip=ip_interface(running_nmstate_vmb.vmi.interfaces[0]["ipAddress"]).ip,
        )

    @pytest.mark.polarion("CNV-3029")
    def test_ping_remote_ip_through_main_interface(
        self,
        worker_nodes_ipv4_false_secondary_nics,
        nmstate_vma,
        nmstate_vmb,
        running_nmstate_vma,
        running_nmstate_vmb,
    ):
        assert_ping_successful(src_vm=running_nmstate_vma, dst_ip=PUBLIC_DNS_SERVER_IP)
