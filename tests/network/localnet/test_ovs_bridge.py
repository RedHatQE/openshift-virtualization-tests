import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.localnet.liblocalnet import (
    LINK_STATE_UP,
    LOCALNET_OVS_BRIDGE_INTERFACE,
    client_server_active_connection,
)
from utilities.constants import QUARANTINED
from utilities.virt import migrate_vm_and_verify


@pytest.mark.ipv4
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: fails in CI due to cluster issue; tracked in CNV-71535",
    run=False,
)
def test_connectivity_over_migration_between_ovs_bridge_localnet_vms(
    localnet_ovs_bridge_server, localnet_ovs_bridge_client
):
    migrate_vm_and_verify(vm=localnet_ovs_bridge_client.vm)
    assert is_tcp_connection(server=localnet_ovs_bridge_server, client=localnet_ovs_bridge_client)


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-12006")
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: fails in CI due to cluster issue; tracked in CNV-71535",
    run=False,
)
def test_connectivity_after_interface_state_change_in_ovs_bridge_localnet_vms(
    ovs_bridge_localnet_running_vms_one_with_interface_down,
):
    (vm1_with_initial_link_down, vm2) = ovs_bridge_localnet_running_vms_one_with_interface_down
    vm1_with_initial_link_down.set_interface_state(network_name=LOCALNET_OVS_BRIDGE_INTERFACE, state=LINK_STATE_UP)

    lookup_iface_status(
        vm=vm1_with_initial_link_down,
        iface_name=LOCALNET_OVS_BRIDGE_INTERFACE,
        predicate=lambda interface: (
            "guest-agent" in interface["infoSource"] and interface["linkState"] == LINK_STATE_UP
        ),
    )

    with client_server_active_connection(
        client_vm=vm2,
        server_vm=vm1_with_initial_link_down,
        spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
