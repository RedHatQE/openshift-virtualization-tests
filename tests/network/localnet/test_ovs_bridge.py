import ipaddress
from ipaddress import ip_interface

import pytest

from libs.net.ip import filter_link_local_addresses, have_same_ip_families
from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from libs.vm.guest import guest_iface_name
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
    ovs_bridge_localnet_active_connections,
):
    client, _ = ovs_bridge_localnet_active_connections[0]
    migrate_vm_and_verify(vm=client.vm)
    for client, server in ovs_bridge_localnet_active_connections:
        with subtests.test(msg=f"IPv{ipaddress.ip_address(client.server_ip).version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-12006")
def test_connectivity_after_interface_state_change_in_ovs_bridge_localnet_vms(
    subtests,
    ovs_bridge_localnet_running_vms_one_with_interface_down,
):
    (vm1_with_initial_link_down, vm2) = ovs_bridge_localnet_running_vms_one_with_interface_down
    vm1_with_initial_link_down.set_interface_state(network_name=LOCALNET_OVS_BRIDGE_INTERFACE, state=LINK_STATE_UP)

    expected_ips = [
        ip_interface(addr).ip
        for addr in vm1_with_initial_link_down.cloud_init_network_data.ethernets[guest_iface_name(ordinal=1)].addresses
    ]
    iface = lookup_iface_status(
        vm=vm1_with_initial_link_down,
        iface_name=LOCALNET_OVS_BRIDGE_INTERFACE,
        predicate=lambda interface: (
            "guest-agent" in interface["infoSource"]
            and interface["linkState"] == LINK_STATE_UP
            and have_same_ip_families(
                actual_ips=filter_link_local_addresses(ip_addresses=interface.get("ipAddresses", [])),
                expected_ips=expected_ips,
            )
        ),
    )

    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm2,
                server_vm=vm1_with_initial_link_down,
                spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
                port=8888,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)
