from typing import Final

import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.localnet.liblocalnet import (
    LINK_STATE_UP,
    LOCALNET_OVS_BRIDGE_NETWORK,
    client_server_active_connection,
)
from utilities.virt import migrate_vm_and_verify

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
def test_connectivity_over_migration_between_ovs_bridge_localnet_vms(
    localnet_ovs_bridge_server, localnet_ovs_bridge_client
):
    migrate_vm_and_verify(vm=localnet_ovs_bridge_client.vm)
    assert is_tcp_connection(server=localnet_ovs_bridge_server, client=localnet_ovs_bridge_client)


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-12006")
def test_connectivity_after_interface_state_change_in_ovs_bridge_localnet_vms(
    ovs_bridge_localnet_running_vms_one_with_interface_down,
):
    ovs_bridge_localnet_running_vms_one_with_interface_down[0].set_interface_state(
        network_name=LOCALNET_OVS_BRIDGE_NETWORK, state=LINK_STATE_UP
    )

    lookup_iface_status(
        vm=ovs_bridge_localnet_running_vms_one_with_interface_down[0],
        iface_name=LOCALNET_OVS_BRIDGE_NETWORK,
        predicate=lambda interface: "guest-agent" in interface["infoSource"]
        and interface["linkState"] == LINK_STATE_UP,
    )

    with client_server_active_connection(
        client_vm=ovs_bridge_localnet_running_vms_one_with_interface_down[1],
        server_vm=ovs_bridge_localnet_running_vms_one_with_interface_down[0],
        spec_logical_network=LOCALNET_OVS_BRIDGE_NETWORK,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
