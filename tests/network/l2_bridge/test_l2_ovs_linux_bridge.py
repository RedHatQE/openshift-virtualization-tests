import logging
import shlex

import pytest
from netaddr import IPNetwork
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from tests.network.libs.dhcpd import DHCP_IP_RANGE_START
from utilities.constants import QUARANTINED, TIMEOUT_2MIN
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name, ping

LOGGER = logging.getLogger(__name__)
CUSTOM_ETH_PROTOCOL = "0x88B6"  # rfc5342 Local Experimental Ethertype. Used to test custom eth type and linux bridge

pytestmark = pytest.mark.usefixtures("hyperconverged_ovs_annotations_enabled_scope_session")


def wait_for_no_packet_loss_after_connection(src_vm, dst_ip, interface=None):
    sleep_count_value = 10

    def _get_ping_state():
        return (
            ping(
                src_vm=src_vm,
                dst_ip=dst_ip,
                count=sleep_count_value,
                interface=interface,
            )
            == 0
        )

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=sleep_count_value,
            func=_get_ping_state,
        ):
            if sample:
                return
    except TimeoutError:
        LOGGER.error(f"Ping from {src_vm.name} to {dst_ip} failed.")
        raise


@pytest.mark.s390x
class TestL2LinuxBridge:
    """
    Test L2 connectivity via linux bridge CNI plugin.
    The main goal is to make sure that different kinds of L2 traffic can pass
    transparently via Linux Bridge.
    """

    @pytest.mark.polarion("CNV-2285")
    def test_connectivity_l2_bridge(
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
        request,
    ):
        """
        Test broadcast traffic via L2 linux bridge. VM_A has dhcp server installed. VM_B dhcp client.
        """
        if "ovs-bridge" in request.node.name:
            pytest.xfail(reason=f"{QUARANTINED}: Test is flaky over OVS bridge, tracked in CNV-70028")
        current_ip = TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=2,
            func=get_vmi_ip_v4_by_name,
            vm=l2_bridge_running_vm_b,
            name=dhcp_nad.name,
        )
        for address in current_ip:
            if str(address) in IPNetwork(f"{DHCP_IP_RANGE_START}/24"):
                return True

    @pytest.mark.ipv4
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
        dst_ip = get_vmi_ip_v4_by_name(vm=l2_bridge_running_vm_b, name=custom_eth_type_llpd_nad.name)
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
        Test multicast traffic(ICMP) via linux bridge
        """
        assert_ping_successful(src_vm=l2_bridge_running_vm_b, dst_ip="224.0.0.1")
