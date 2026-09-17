from __future__ import annotations

import ipaddress
import itertools
from ipaddress import ip_interface
from typing import TYPE_CHECKING

import pytest

from libs.net.ip import filter_cluster_unsupported_addresses, filter_link_local_addresses, have_same_ip_families
from libs.net.traffic_generator import active_tcp_connections, client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.localnet import (
    GUEST_2ND_IFACE_NAME,
    LOCALNET_BR_EX_INTERFACE,
    LOCALNET_BR_EX_INTERFACE_NO_VLAN,
)
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.net.traffic_generator import TcpServer, VMTcpClient
    from libs.vm.vm import BaseVirtualMachine


@pytest.mark.gating
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11775")
def test_connectivity_over_migration_between_localnet_vms(
    admin_client: DynamicClient,
    subtests: pytest.Subtests,
    localnet_active_connections: list[tuple[VMTcpClient, TcpServer]],
):
    client, _ = localnet_active_connections[0]
    migrate_vm_and_verify(vm=client.vm, client=admin_client)
    for client, server in localnet_active_connections:
        with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11925")
def test_connectivity_post_migration_between_localnet_vms(
    subtests,
    migrated_localnet_vm,
    localnet_running_vms,
):
    vms = list(localnet_running_vms)
    vms.remove(migrated_localnet_vm)
    (base_localnet_vm,) = vms

    iface = lookup_iface_status(vm=migrated_localnet_vm, iface_name=LOCALNET_BR_EX_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=base_localnet_vm,
                server_vm=migrated_localnet_vm,
                spec_logical_network=LOCALNET_BR_EX_INTERFACE,
                port=8888,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-12363")
def test_vmi_reports_ip_on_secondary_interface_without_vlan(
    localnet_running_vms,
):
    """
    Test that vm_localnet_1's secondary interface on a no-VLAN localnet
    correctly reports the IP addresses for that interface based on cluster network stack.
    """
    vm, _ = localnet_running_vms

    expected_ips = [
        ip_interface(addr).ip for addr in vm.cloud_init_network_data.ethernets[GUEST_2ND_IFACE_NAME].addresses
    ]
    iface_status = lookup_iface_status(
        vm=vm,
        iface_name=LOCALNET_BR_EX_INTERFACE_NO_VLAN,
        predicate=lambda interface: have_same_ip_families(
            actual_ips=filter_cluster_unsupported_addresses(
                ip_addresses=filter_link_local_addresses(
                    ip_addresses=[str(ip_interface(addr).ip) for addr in interface["ipAddresses"]]
                )
            ),
            expected_ips=expected_ips,
        ),
    )
    reported_ips = filter_cluster_unsupported_addresses(
        ip_addresses=filter_link_local_addresses(
            ip_addresses=[str(ip_interface(addr).ip) for addr in iface_status.ipAddresses]
        )
    )
    assert set(reported_ips) == set(expected_ips), (
        f"IP addresses mismatch for interface {LOCALNET_BR_EX_INTERFACE_NO_VLAN} on VM {vm.name}, "
        f"Reported: {reported_ips}, Expected: {expected_ips}"
    )


@pytest.mark.single_nic
@pytest.mark.incremental
@pytest.mark.usefixtures("nncp_localnet")
class TestSharedHostnameLocalnet:
    """Tests for VMs sharing the same spec.template.spec.hostname on localnet.

    Jira: https://issues.redhat.com/browse/OCPBUGS-99277 # <skip-jira-utils-check>

    Preconditions:
        - 3 VMs with identical spec.template.spec.hostname connected to a localnet secondary network
        - All 3 VMs Running with IPs assigned on the localnet interface
    """

    @pytest.mark.polarion("CNV-16555")
    def test_tcp_connectivity_between_shared_hostname_vms(
        self,
        subtests: pytest.Subtests,
        running_shared_hostname_vms: list[BaseVirtualMachine],
    ):
        """Test that VMs sharing the same hostname can communicate over localnet.

        Preconditions:
            - 3 VMs with identical spec.template.spec.hostname connected to a localnet secondary network
            - All 3 VMs Running with IPs assigned on the localnet interface

        Steps:
            1. For each pair of VMs, establish a TCP connection over the localnet interface

        Expected:
            - TCP connectivity succeeds between all VM pairs
        """
        for client_vm, server_vm in itertools.combinations(running_shared_hostname_vms, 2):
            with active_tcp_connections(
                client_vm=client_vm,
                server_vm=server_vm,
                iface_name=LOCALNET_BR_EX_INTERFACE,
            ) as connections:
                for client, server in connections:
                    with subtests.test(
                        msg=f"{client_vm.name} -> {server_vm.name} IPv{ipaddress.ip_address(client.server_ip).version}"
                    ):
                        assert is_tcp_connection(server=server, client=client), (
                            f"TCP connection failed: {client_vm.name} -> {server_vm.name} ({client.server_ip})"
                        )

    @pytest.mark.polarion("CNV-16556")
    def test_tcp_connectivity_after_migration_of_shared_hostname_vm(
        self,
        subtests: pytest.Subtests,
        admin_client: DynamicClient,
        running_shared_hostname_vms: list[BaseVirtualMachine],
    ):
        """Test that connectivity is preserved after migrating a VM that shares its hostname.

        Preconditions:
            - 3 VMs with identical spec.template.spec.hostname connected to a localnet secondary network
            - All 3 VMs Running with IPs assigned on the localnet interface

        Steps:
            1. Migrate one of the shared-hostname VMs
            2. Establish TCP connections from the migrated VM to each of the other VMs

        Expected:
            - TCP connectivity succeeds from the migrated VM to all other VMs
        """
        migrated_vm = running_shared_hostname_vms[0]
        migrate_vm_and_verify(vm=migrated_vm, client=admin_client)

        for peer_vm in running_shared_hostname_vms[1:]:
            with active_tcp_connections(
                client_vm=migrated_vm,
                server_vm=peer_vm,
                iface_name=LOCALNET_BR_EX_INTERFACE,
            ) as connections:
                for client, server in connections:
                    with subtests.test(
                        msg=f"migrated {migrated_vm.name} -> {peer_vm.name}"
                        f" IPv{ipaddress.ip_address(client.server_ip).version}"
                    ):
                        assert is_tcp_connection(server=server, client=client), (
                            f"TCP connection failed after migration:"
                            f" {migrated_vm.name} -> {peer_vm.name} ({client.server_ip})"
                        )
