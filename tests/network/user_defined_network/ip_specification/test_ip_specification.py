"""
IP addresses specification on a VM

Tests are aimed to cover the ability to define at VM definition its primary UDN IP address.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

import pytest

from libs.net.traffic_generator import TcpServer, client_server_active_connection, is_tcp_connection
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import read_guest_interface_ipv4
from tests.network.user_defined_network.ip_specification.libipspec import ip_address_annotation
from utilities.constants.networking import PUBLIC_DNS_SERVER_IP
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.incremental
class TestVMWithExplicitIPAddressSpecification:
    """
    Tests for VM with an IP address explicitly defined for the primary UDN.

    Markers:
        - IPv4
        - single_nic
        - incremental

    Preconditions:
        - UDN supported namespace.
        - UDN resource for the primary network (with an IP range defined).
        - Base halted under-test VM with a primary UDN network.
        - Base running connectivity reference VM with a primary UDN network.
    """

    @pytest.mark.polarion("CNV-13120")
    def test_vm_is_started_with_successful_connectivity(
        self,
        vm_under_test: BaseVirtualMachine,
        vm_for_connectivity_ref: BaseVirtualMachine,
        ip_to_request: ipaddress.IPv4Interface | ipaddress.IPv6Interface,
    ) -> None:
        """
        Test that a VM with an explicit IP address specified is started successfully and is reachable.

        Preconditions:
            - Stopped under-test VM, with a primary UDN network (no IP address specified).
            - Running connectivity reference VM, with a primary UDN network.
            - IP address to specify on under-test VM.

        Steps:
            1. Set IP address on under-test VM through annotation.
            2. Start the VM and wait for the Ip to be reported on the VMI status.
            3. Establish TCP connectivity from the ref VM to the under-test VM.

        Expected:
            - IP address reported by VMI status and guest OS is the same as the one specified.
            - Verify that the VM is reachable from the ref VM.
        """
        vm_logical_net_name = lookup_primary_network(vm=vm_under_test).name
        vm_under_test.update_template_annotations(
            template_annotations=ip_address_annotation(ip_address=ip_to_request, network_name=vm_logical_net_name)
        )

        vm_under_test.start()
        vm_under_test.wait_for_agent_connected()
        assigned_ip = lookup_iface_status_ip(vm=vm_under_test, iface_name=vm_logical_net_name, ip_family=4)

        assert assigned_ip == ip_to_request.ip
        guest_ipv4 = read_guest_interface_ipv4(
            vm=vm_under_test,
            interface_name=vm_under_test.vmi.interfaces[0].interfaceName,
        )
        assert guest_ipv4 == ip_to_request

        with client_server_active_connection(
            client_vm=vm_for_connectivity_ref,
            server_vm=vm_under_test,
            spec_logical_network=vm_logical_net_name,
        ) as (client, server):
            assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-12582")
    def test_successful_external_connectivity(self, vm_under_test: BaseVirtualMachine) -> None:
        """
        Test that a VM with an explicit IP address specified is reaching an external IP address.

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation).

        Steps:
            1. Execute a ping command from the under-test VM to the external IP address.

        Expected:
            - Verify that the ping command succeeds with 0% packet loss.
        """
        assert vm_under_test.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=30)

    @pytest.mark.polarion("CNV-12586")
    def test_seamless_cluster_connectivity_is_preserved_over_live_migration(
        self,
        admin_client: DynamicClient,
        client_server_tcp_connectivity_between_vms: tuple[TcpClient, TcpServer],
    ):
        """
        Test that a VM with an explicit IP address specified can preserve connectivity during live migration.

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation).
            - Running connectivity reference VM, with a primary UDN network.
            - Established TCP connectivity from the ref VM to the under-test VM.

        Steps:
            1. Migrate the under-test VM (and wait for completion).

        Expected:
            - The initial TCP connection is preserved (no disconnection).
        """
        client, server = client_server_tcp_connectivity_between_vms

        migrate_vm_and_verify(vm=server.vm, client=admin_client)

        assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-12585")
    def test_ip_address_is_preserved_over_power_cycle(
        self,
        vm_under_test: BaseVirtualMachine,
        ip_to_request: ipaddress.IPv4Interface | ipaddress.IPv6Interface,
    ) -> None:
        """
        Test that a VM with an explicit IP address specified can preserve its IP address over a power cycle
        (VM is stopped and started again).

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation).
            - The specified IP address on the under-test VM.

        Steps:
            1. Restart the under-test VM (and wait for completion).

        Expected:
            - IP address reported by VMI status and guest OS is the same as the one specified.
        """
        vm_under_test.restart(wait=True)
        vm_under_test.wait_for_agent_connected()

        vm_logical_net_name = lookup_primary_network(vm=vm_under_test).name
        assigned_ip = lookup_iface_status_ip(vm=vm_under_test, iface_name=vm_logical_net_name, ip_family=4)

        assert assigned_ip == ip_to_request.ip
        guest_ipv4 = read_guest_interface_ipv4(
            vm=vm_under_test,
            interface_name=vm_under_test.vmi.interfaces[0].interfaceName,
        )
        assert guest_ipv4 == ip_to_request
