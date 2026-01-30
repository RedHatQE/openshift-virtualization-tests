"""
BGP Connectivity Tests

Tests for verifying connectivity between CUDN (Cluster User-Defined Network) VMs
and external networks using BGP routing.

STP Reference:
# TODO: Add link to Polarion STP
"""

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
    """
    Test that CUDN VM can establish TCP connection with external network.

    Markers:
        - bgp
        - ipv4

    Preconditions:
        - BGP setup configured
        - TCP server running on CUDN VM
        - TCP client on external network

    Steps:
        1. Establish TCP connection from external client to CUDN VM server

    Expected:
        - TCP connection succeeds
    """
    assert is_tcp_connection(server=tcp_server_cudn_vm, client=tcp_client_external_network)


@pytest.mark.polarion("CNV-12281")
def test_connectivity_is_preserved_during_cudn_vm_migration(
    tcp_server_cudn_vm,
    tcp_client_external_network,
):
    """
    Test that TCP connectivity is preserved after CUDN VM migration.

    Markers:
        - bgp
        - ipv4

    Preconditions:
        - BGP setup configured
        - TCP server running on CUDN VM
        - TCP client on external network

    Steps:
        1. Migrate CUDN VM
        2. Establish TCP connection

    Expected:
        - TCP connection succeeds after migration
    """
    migrate_vm_and_verify(vm=tcp_server_cudn_vm.vm)
    assert is_tcp_connection(server=tcp_server_cudn_vm, client=tcp_client_external_network)
