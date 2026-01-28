import pytest

from libs.net.traffic_generator import is_tcp_connection
from utilities.virt import migrate_vm_and_verify

pytestmark = [
    pytest.mark.bgp,
    pytest.mark.ipv4,
    pytest.mark.usefixtures("bgp_setup_ready"),
]


@pytest.mark.polarion("CNV-12276")
def test_connectivity_cudn_vm_and_external_network(tcp_server_cudn_vm, tcp_client_external_network):
    assert is_tcp_connection(server=tcp_server_cudn_vm, client=tcp_client_external_network)


@pytest.mark.polarion("CNV-12281")
def test_connectivity_is_preserved_during_cudn_vm_migration(
    tcp_server_cudn_vm,
    tcp_client_external_network,
):
    migrate_vm_and_verify(vm=tcp_server_cudn_vm.vm)
    assert is_tcp_connection(server=tcp_server_cudn_vm, client=tcp_client_external_network)
