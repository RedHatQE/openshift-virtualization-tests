import pytest

from libs.net.traffic_generator import is_tcp_connection
from tests.network.localnet.liblocalnet import LOCALNET_BR_EX_NETWORK, client_server_active_connection
from utilities.virt import migrate_vm_and_verify


@pytest.mark.gating
@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11775")
def test_connectivity_over_migration_between_localnet_vms(localnet_server, localnet_client):
    migrate_vm_and_verify(vm=localnet_client.vm)
    assert is_tcp_connection(server=localnet_server, client=localnet_client)


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11925")
def test_connectivity_post_migration_between_localnet_vms(migrated_localnet_vm, localnet_running_vms):
    vms = list(localnet_running_vms)
    vms.remove(migrated_localnet_vm)
    (base_localnet_vm,) = vms

    with client_server_active_connection(
        client_vm=base_localnet_vm,
        server_vm=migrated_localnet_vm,
        spec_logical_network=LOCALNET_BR_EX_NETWORK,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
