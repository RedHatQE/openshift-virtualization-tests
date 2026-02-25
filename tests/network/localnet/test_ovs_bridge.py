import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.ip import filter_link_local_addresses
from tests.network.localnet.liblocalnet import (
    LINK_STATE_UP,
    LOCALNET_OVS_BRIDGE_INTERFACE,
)
from utilities.virt import migrate_vm_and_verify


@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
def test_connectivity_over_migration_between_ovs_bridge_localnet_vms(
    subtests,
    ovs_bridge_localnet_running_vms,
    ovs_bridge_localnet_active_connections,
):
    _, client_vm = ovs_bridge_localnet_running_vms
    migrate_vm_and_verify(vm=client_vm)
    for dst_ip, client, server in ovs_bridge_localnet_active_connections:
        with subtests.test(msg=f"TCP iperf3 over IPv{dst_ip.version} during migration"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-12006")
def test_connectivity_after_interface_state_change_in_ovs_bridge_localnet_vms(
    subtests,
    ovs_bridge_localnet_running_vms_one_with_interface_down,
):
    (vm1_with_initial_link_down, vm2) = ovs_bridge_localnet_running_vms_one_with_interface_down
    vm1_with_initial_link_down.set_interface_state(network_name=LOCALNET_OVS_BRIDGE_INTERFACE, state=LINK_STATE_UP)

    iface = lookup_iface_status(
        vm=vm1_with_initial_link_down,
        iface_name=LOCALNET_OVS_BRIDGE_INTERFACE,
        predicate=lambda interface: (
            "guest-agent" in interface["infoSource"]
            and interface["linkState"] == LINK_STATE_UP
            and interface.get("ipAddresses")
        ),
    )

    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"TCP iperf3 over IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm2,
                server_vm=vm1_with_initial_link_down,
                spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
                port=8888,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)
