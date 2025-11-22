import pytest

from libs.net.traffic_generator import is_tcp_connection
from tests.network.libs.ip import ICMPV4_HEADER_SIZE, IPV4_HEADER_SIZE, TCP_HEADER_SIZE
from tests.network.localnet.liblocalnet import LOCALNET_OVS_BRIDGE_INTERFACE, create_traffic_client
from utilities.network import get_vmi_ip_v4_by_name
from utilities.virt import vm_console_run_commands


@pytest.mark.polarion("CNV-12349")
@pytest.mark.parametrize("cudn_localnet_ovs_bridge", [{"mtu": "cluster_hardware_mtu"}], indirect=True)
@pytest.mark.parametrize("nncp_localnet_on_secondary_node_nic", [{"mtu": "cluster_hardware_mtu"}], indirect=True)
@pytest.mark.jumbo_frame
def test_connectivity_ovs_bridge_jumbo_frames_no_fragmentation(
    cluster_hardware_mtu,
    cudn_localnet_ovs_bridge,
    nncp_localnet_on_secondary_node_nic,
    ovs_bridge_localnet_running_vms,
    localnet_ovs_bridge_server,
):
    ping_packet_size = cluster_hardware_mtu - ICMPV4_HEADER_SIZE - IPV4_HEADER_SIZE
    vm1, vm2 = ovs_bridge_localnet_running_vms
    dst_ip = get_vmi_ip_v4_by_name(vm=vm2, name=LOCALNET_OVS_BRIDGE_INTERFACE)
    ping_cmd_jumbo_frame_no_fragmentation = f"ping -q -c 3 {dst_ip} -s {ping_packet_size} -M do"
    vm_console_run_commands(vm=vm1, commands=[ping_cmd_jumbo_frame_no_fragmentation])

    with create_traffic_client(
        server_vm=vm1,
        client_vm=vm2,
        spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
        maximum_segment_size=cluster_hardware_mtu - IPV4_HEADER_SIZE - TCP_HEADER_SIZE,
    ) as client:
        assert is_tcp_connection(server=localnet_ovs_bridge_server, client=client)
