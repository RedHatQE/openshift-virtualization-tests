from typing import Final

import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status, lookup_iface_status_ip, lookup_primary_network
from tests.network.localnet.liblocalnet import client_server_active_connection
from utilities.constants import PUBLIC_DNS_SERVER_IP
from utilities.virt import migrate_vm_and_verify

SERVER_PORT: Final[int] = 1234
VM_CONSOLE_CMD_TIMEOUT: Final[int] = 20

pytestmark = [pytest.mark.mtv, pytest.mark.ipv4]


@pytest.mark.polarion("CNV-12208")
def test_mac_and_ip_preserved_after_vm_import(source_vm_network_data, imported_cudn_vm, subtests):
    source_vm_mac, source_vm_ip = source_vm_network_data
    target_vm_iface = lookup_iface_status(
        vm=imported_cudn_vm, iface_name=lookup_primary_network(vm=imported_cudn_vm).name
    )
    target_vm_mac = target_vm_iface.get("mac", None)
    target_vm_ip = str(
        lookup_iface_status_ip(
            vm=imported_cudn_vm, iface_name=lookup_primary_network(vm=imported_cudn_vm).name, ip_family=4
        )
    )

    with subtests.test("MAC preserved"):
        assert source_vm_mac == target_vm_mac, (
            f"The MAC address was not preserved during VM import. Expected: {source_vm_mac}, got: {target_vm_mac}."
        )
    with subtests.test("IP preserved"):
        assert source_vm_ip == target_vm_ip, (
            f"The IP address was not preserved during VM import. Expected: {source_vm_ip}, got: {target_vm_ip}."
        )


@pytest.mark.polarion("CNV-12207")
def test_imported_vm_egress_connectivity(imported_cudn_vm):
    imported_cudn_vm.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=VM_CONSOLE_CMD_TIMEOUT)


@pytest.mark.polarion("CNV-12212")
def test_connectivity_between_imported_and_local_vms(imported_cudn_vm, local_cudn_vm):
    with client_server_active_connection(
        client_vm=imported_cudn_vm,
        server_vm=local_cudn_vm,
        spec_logical_network=lookup_primary_network(vm=local_cudn_vm).name,
        port=SERVER_PORT,
    ) as (client, server):
        assert is_tcp_connection(server=server, client=client), "TCP connection between imported VM and local VM failed"


@pytest.mark.polarion("CNV-12579")
def test_connectivity_over_inner_migration_between_imported_and_local_vms(
    admin_client, imported_cudn_vm, local_cudn_vm
):
    with client_server_active_connection(
        client_vm=imported_cudn_vm,
        server_vm=local_cudn_vm,
        spec_logical_network=lookup_primary_network(vm=local_cudn_vm).name,
        port=SERVER_PORT,
    ) as (client, server):
        migrate_vm_and_verify(vm=imported_cudn_vm, client=admin_client)
        assert is_tcp_connection(server=server, client=client), (
            "TCP connection between imported VM and local VM failed over imported VM inner migration"
        )
