from ipaddress import ip_address, ip_interface

import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import IP_ADDRESS, lookup_iface_status
from tests.network.localnet.liblocalnet import (
    LOCALNET_BR_EX_INTERFACE,
    LOCALNET_BR_EX_INTERFACE_NO_VLAN,
    client_server_active_connection,
)
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
        spec_logical_network=LOCALNET_BR_EX_INTERFACE,
        port=8888,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client)


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-12363")
def test_vmi_reports_ip_on_secondary_interface_without_vlan(
    localnet_running_vms,
    vm_localnet_1_secondary_ip,
):
    """
    Test that vm_localnet_1's secondary interface on a no-VLAN localnet
    correctly reports the IP address for that interface.
    """
    vm, _ = localnet_running_vms
    interface_status = lookup_iface_status(vm=vm, iface_name=LOCALNET_BR_EX_INTERFACE_NO_VLAN)
    assert ip_address(interface_status[IP_ADDRESS]) == ip_interface(vm_localnet_1_secondary_ip).ip, (
        f"IP address mismatch for interface {LOCALNET_BR_EX_INTERFACE_NO_VLAN} on VM {vm.name}, "
        f"interface status: {interface_status}"
    )
