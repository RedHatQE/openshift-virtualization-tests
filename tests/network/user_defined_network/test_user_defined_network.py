from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

import pytest
from ocp_resources.utils.constants import TIMEOUT_1MINUTE

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from utilities.constants.networking import PUBLIC_DNS_SERVER_IP
from utilities.constants.pytest import QUARANTINED
from utilities.constants.timeouts import TIMEOUT_1MIN
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.net.traffic_generator import TcpServer, VMTcpClient
    from libs.vm.vm import BaseVirtualMachine


@pytest.mark.ipv4
@pytest.mark.s390x
@pytest.mark.single_nic
class TestPrimaryUdn:
    @pytest.mark.polarion("CNV-11624")
    def test_ip_address_in_running_vm_matches_udn_subnet(self, namespaced_layer2_user_defined_network, vma_udn):
        ip = str(lookup_iface_status_ip(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name, ip_family=4))
        (subnet,) = namespaced_layer2_user_defined_network.subnets
        assert ipaddress.ip_address(ip) in ipaddress.ip_network(subnet), (
            f"The VM's primary network IP address ({ip}) is not in the UDN defined subnet ({subnet})"
        )

    @pytest.mark.polarion("CNV-11674")
    def test_ip_address_is_preserved_after_live_migration(
        self, admin_client: DynamicClient, vma_udn: BaseVirtualMachine
    ):
        ip_before_migration = str(
            lookup_iface_status_ip(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name, ip_family=4)
        )
        assert ip_before_migration
        migrate_vm_and_verify(vm=vma_udn, client=admin_client)
        ip_after_migration = str(
            lookup_iface_status_ip(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name, ip_family=4)
        )
        assert ip_before_migration == ip_after_migration, (
            f"The IP address {ip_before_migration} was not preserved during live migration. "
            f"IP after migration: {ip_after_migration}."
        )

    @pytest.mark.polarion("CNV-11434")
    def test_vm_egress_connectivity(self, vmb_udn):
        assert str(lookup_iface_status_ip(vm=vmb_udn, iface_name=lookup_primary_network(vm=vmb_udn).name, ip_family=4))
        vmb_udn.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=TIMEOUT_1MINUTE)

    @pytest.mark.polarion("CNV-11418")
    def test_basic_connectivity_between_udn_vms(self, vma_udn, vmb_udn):
        target_vm_ip = str(
            lookup_iface_status_ip(vm=vmb_udn, iface_name=lookup_primary_network(vm=vmb_udn).name, ip_family=4)
        )
        vma_udn.console(commands=[f"ping -c 3 {target_vm_ip}"], timeout=TIMEOUT_1MIN)

    @pytest.mark.polarion("CNV-11427")
    @pytest.mark.gating
    def test_connectivity_is_preserved_during_client_live_migration(
        self, admin_client: DynamicClient, server: TcpServer, client: VMTcpClient
    ):
        migrate_vm_and_verify(vm=client.vm, client=admin_client)
        assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-12177")
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Failed migration of vm in UDN: CNV-72782",
        run=False,
    )
    def test_connectivity_is_preserved_during_server_live_migration(
        self, admin_client: DynamicClient, server: TcpServer, client: VMTcpClient
    ):
        migrate_vm_and_verify(vm=server.vm, client=admin_client)
        assert is_tcp_connection(server=server, client=client)
