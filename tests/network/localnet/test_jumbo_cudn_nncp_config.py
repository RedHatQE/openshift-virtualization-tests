import pytest

from libs.net.traffic_generator import is_tcp_connection
from tests.network.localnet.liblocalnet import ICMP_HEADER, IP_HEADER
from utilities.network import get_vmi_ip_v4_by_name
from utilities.virt import vm_console_run_commands


@pytest.mark.polarion("CNV-12349")
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic_config_mtu")
def test_tcp_connectivity_ovs_bridge_jumbo_frames_no_fragmentation(
    cudn_localnet_ovs_bridge_jumbo_frame,
    ovs_bridge_localnet_running_jumbo_frame_vms,
    localnet_ovs_bridge_jumbo_frame_server,
    localnet_ovs_bridge_jumbo_frame_client,
    cluster_hardware_mtu,
):
    ping_packet_size = cluster_hardware_mtu - ICMP_HEADER - IP_HEADER
    vm1, vm2 = ovs_bridge_localnet_running_jumbo_frame_vms
    dst_ip = get_vmi_ip_v4_by_name(vm=vm2, name=cudn_localnet_ovs_bridge_jumbo_frame.name)
    ping_cmd_jumbo_frame_no_fragmentation = f"ping -q -c 3 {dst_ip} -s {ping_packet_size} -M do"
    vm_console_run_commands(vm=vm1, commands=[ping_cmd_jumbo_frame_no_fragmentation])

    assert is_tcp_connection(
        server=localnet_ovs_bridge_jumbo_frame_server, client=localnet_ovs_bridge_jumbo_frame_client
    )
