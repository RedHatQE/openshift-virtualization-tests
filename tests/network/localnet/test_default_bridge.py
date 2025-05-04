import pytest

from libs.net.traffic_generator import is_tcp_connection
from utilities.virt import migrate_vm_and_verify


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11775")
def test_connectivity_over_migration_between_localnet_vms(localnet_server, localnet_client):
    migrate_vm_and_verify(vm=localnet_client.vm)
    assert is_tcp_connection(server=localnet_server, client=localnet_client)
