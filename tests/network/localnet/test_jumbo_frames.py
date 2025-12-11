import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs.ip import ICMPV4_HEADER_SIZE, IPV4_HEADER_SIZE
from tests.network.localnet.liblocalnet import LOCALNET_OVS_BRIDGE_INTERFACE
from utilities.virt import vm_console_run_commands

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.jumbo_frame,
]


@pytest.mark.polarion("CNV-12349")
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic_with_jumbo_frame")
def test_connectivity_ovs_bridge_jumbo_frames_no_fragmentation(
    cluster_hardware_mtu,
    ovs_bridge_localnet_running_jumbo_frame_vms,
    localnet_ovs_bridge_jumbo_frame_client_and_server_vms,
):
    ping_payload_size = cluster_hardware_mtu - ICMPV4_HEADER_SIZE - IPV4_HEADER_SIZE
    vm1, vm2 = ovs_bridge_localnet_running_jumbo_frame_vms
    dst_ip = lookup_iface_status_ip(vm=vm2, iface_name=LOCALNET_OVS_BRIDGE_INTERFACE, ip_family=4)
    ping_cmd_jumbo_frame_no_fragmentation = f"ping -q -c 3 {dst_ip} -s {ping_payload_size} -M do"
    vm_console_run_commands(vm=vm1, commands=[ping_cmd_jumbo_frame_no_fragmentation])

    client, server = localnet_ovs_bridge_jumbo_frame_client_and_server_vms
    assert is_tcp_connection(server=server, client=client)
