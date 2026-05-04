import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.vm.vm import BaseVirtualMachine
from tests.network.localnet.liblocalnet import LOCALNET_IPAM_INTERFACE


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-14043")
def test_tcp_connectivity_between_vms_with_localnet_ipam_nic(
    localnet_ipam_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
):
    """
    Verify TCP connectivity between VMs with localnet IPAM.

    Preconditions:
    - Client VM and server VM with localnet bridge interfaces attached via NAD with IPAM enabled.

    Steps:
    1. Establish TCP connection between the client VM and server VM over the localnet IPAM interface.

    Expected:
    - TCP connectivity is successfully established between the two VMs using DHCP-assigned IP addresses.
    """
    vm1, vm2 = localnet_ipam_running_vms

    with client_server_active_connection(
        client_vm=vm1,
        server_vm=vm2,
        spec_logical_network=LOCALNET_IPAM_INTERFACE,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)
