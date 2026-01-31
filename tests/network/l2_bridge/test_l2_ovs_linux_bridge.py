import shlex

import pytest
from netaddr import IPNetwork
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.l2_bridge.libl2bridge import wait_for_no_packet_loss_after_connection
from tests.network.libs.dhcpd import DHCP_IP_RANGE_START
from utilities.constants import TIMEOUT_2MIN
from utilities.network import assert_ping_successful

pytestmark = [pytest.mark.ipv4, pytest.mark.usefixtures("hyperconverged_ovs_annotations_enabled_scope_session")]

CUSTOM_ETH_PROTOCOL = "0x88B6"  # rfc5342 Local Experimental Ethertype. Used to test custom eth type


@pytest.mark.s390x
class TestL2Bridge:
    """
    Test L2 connectivity via Linux or OVS bridge CNI plugin.
    Each bridge is configured by fixtures with matrix.
    The main goal is to make sure that different kinds of L2 traffic can pass
    transparently via Linux/OVS Bridge.
    """

    @pytest.mark.polarion("CNV-2285")
    def test_mpls_connectivity_l2_bridge(
        self,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_a,
        l2_bridge_running_vm_b,
    ):
        """
        Test VM to VM connectivity via mpls
        """
        wait_for_no_packet_loss_after_connection(
            src_vm=l2_bridge_running_vm_a,
            dst_ip=l2_bridge_running_vm_b.mpls_local_ip,
        )

    @pytest.mark.polarion("CNV-2282")
    def test_dhcp_broadcast(
        self,
        dhcp_nad,
        l2_bridge_running_vm_b,
        configured_l2_bridge_vm_a,
        started_vmb_dhcp_client,
    ):
        """
        Test broadcast traffic via L2 bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """
        current_ip = TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=2,
            func=lookup_iface_status_ip,
            vm=l2_bridge_running_vm_b,
            iface_name=dhcp_nad.name,
            ip_family=4,
        )
        for address in current_ip:
            if str(address) in IPNetwork(f"{DHCP_IP_RANGE_START}/24"):
                return True

    @pytest.mark.polarion("CNV-2284")
    def test_custom_eth_type(
        self,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
        custom_eth_type_llpd_nad,
    ):
        """
        Test custom type field in ethernet header.
        """
        num_of_packets = 10
        dst_ip = lookup_iface_status_ip(
            vm=l2_bridge_running_vm_b, iface_name=custom_eth_type_llpd_nad.name, ip_family=4
        )
        out = run_ssh_commands(
            host=configured_l2_bridge_vm_a.ssh_exec,
            commands=[shlex.split(f"nping -e eth2 --ether-type {CUSTOM_ETH_PROTOCOL} {dst_ip} -c {num_of_packets} &")],
        )[0]
        assert f"Successful connections: {num_of_packets}" in out

    @pytest.mark.polarion("CNV-2674")
    def test_icmp_multicast(
        self,
        configured_l2_bridge_vm_a,
        l2_bridge_running_vm_b,
    ):
        """
        Test multicast traffic(ICMP) via L2 bridge
        """
        assert_ping_successful(src_vm=l2_bridge_running_vm_b, dst_ip="224.0.0.1")
