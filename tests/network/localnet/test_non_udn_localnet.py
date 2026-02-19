import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.vm.vm import BaseVirtualMachine


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-14043")
def test_tcp_connectivity_between_vms_with_localnet_primary_ipam_nic(
    primary_localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
):
    """
    Verify TCP connectivity between two VMs connected via localnet NAD, with IPAM, on primary NIC.

    This test verifies that two VMs with primary interfaces bound to a localnet bridge
    can communicate over TCP using DHCP-assigned IP addresses from the NAD subnet configuration.
    """
    vm1, vm2 = primary_localnet_running_vms

    with client_server_active_connection(
        client_vm=vm1,
        server_vm=vm2,
        spec_logical_network="eth0",
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
