import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.ip import (
    ICMP_HEADER_SIZE,
    TCP_HEADER_SIZE,
    filter_link_local_addresses,
    ip_header_size,
)
from tests.network.localnet.liblocalnet import LOCALNET_OVS_BRIDGE_INTERFACE
from utilities.virt import vm_console_run_commands

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.jumbo_frame,
]


@pytest.mark.polarion("CNV-12349")
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic_with_jumbo_frame")
def test_connectivity_ovs_bridge_jumbo_frames_no_fragmentation(
    subtests,
    cluster_hardware_mtu,
    ovs_bridge_localnet_running_jumbo_frame_vms,
):
    vm1, vm2 = ovs_bridge_localnet_running_jumbo_frame_vms
    iface = lookup_iface_status(vm=vm2, iface_name=LOCALNET_OVS_BRIDGE_INTERFACE, timeout=120)
    vm2_addresses = filter_link_local_addresses(ip_addresses=iface.ipAddresses)

    for dst_ip in vm2_addresses:
        ping_payload_size = cluster_hardware_mtu - ip_header_size(ip=dst_ip) - ICMP_HEADER_SIZE
        with subtests.test(msg=f"Jumbo frame ping to IPv{dst_ip.version} {dst_ip}"):
            vm_console_run_commands(
                vm=vm1,
                commands=[f"ping{' -6' if dst_ip.version == 6 else ''} -q -c 3 {dst_ip} -s {ping_payload_size} -M do"],
            )

    for dst_ip in vm2_addresses:
        with subtests.test(msg=f"TCP iperf3 over IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm2,
                server_vm=vm1,
                spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
                maximum_segment_size=cluster_hardware_mtu - ip_header_size(ip=dst_ip) - TCP_HEADER_SIZE,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)
