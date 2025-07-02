import pytest

from libs.net.traffic_generator import is_tcp_connection
from utilities.virt import migrate_vm_and_verify


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
@pytest.mark.s390x
def test_connectivity_over_migration_between_ovs_bridge_localnet_vms(
    localnet_ovs_bridge_server, localnet_ovs_bridge_client
):
    migrate_vm_and_verify(vm=localnet_ovs_bridge_client.vm)
    assert is_tcp_connection(server=localnet_ovs_bridge_server, client=localnet_ovs_bridge_client)
