import pytest

from libs.net import netattachdef as libnad
from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.vm.vm import BaseVirtualMachine
from tests.network.localnet.liblocalnet import LOCALNET_IPAM_INTERFACE


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-14043")
def test_tcp_connectivity_between_vms_with_localnet_ipam_nic(
    ipam_localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    nad_localnet_secondary_node_nic: libnad.NetworkAttachmentDefinition,
):
    """
    Verify TCP connectivity between the interfaces of two VMs, connected via localnet NAD, with IPAM.

    This test verifies that two VMs with interfaces bound to a localnet bridge can communicate over
    TCP using DHCP-assigned IP addresses from the NAD subnet configuration.
    """
    vm1, vm2 = ipam_localnet_running_vms

    with client_server_active_connection(
        client_vm=vm1,
        server_vm=vm2,
        spec_logical_network=LOCALNET_IPAM_INTERFACE,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
