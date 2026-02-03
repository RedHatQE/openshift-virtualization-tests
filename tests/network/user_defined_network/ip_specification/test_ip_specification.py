"""
IP addresses specification on a VM

Tests are aimed to cover the ability to define at VM definition its primary UDN IP address.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md
"""

import ipaddress
from typing import Final

import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.user_defined_network.ip_specification.libipspec import (
    ip_address_annotation,
    read_guest_interface_ipv4,
)
from utilities.constants import PUBLIC_DNS_SERVER_IP

FIRST_GUEST_IFACE_NAME: Final[str] = "eth0"


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
            1. Set IP address on under-test VM through annotation and cloud-init network-data.
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

        netdata = cloudinit.NetworkData(
            ethernets={
                FIRST_GUEST_IFACE_NAME: cloudinit.EthernetDevice(
                    addresses=[str(ip_to_request)],
                    gateway4=str(next(ipaddress.ip_network(address=ip_to_request, strict=False).hosts())),
                )
            }
        )
        vm_under_test.add_cloud_init(netdata=netdata)

        vm_under_test.start()
        vm_under_test.wait_for_agent_connected()
        assigned_ip = lookup_iface_status_ip(vm=vm_under_test, iface_name=vm_logical_net_name, ip_family=4)

        assert assigned_ip == ip_to_request.ip
        assert read_guest_interface_ipv4(vm=vm_under_test, interface_name=FIRST_GUEST_IFACE_NAME) == ip_to_request

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
              (through annotation & cloud-init).

        Steps:
            1. Execute a ping command from the under-test VM to the external IP address.

        Expected:
            - Verify that the ping command succeeds with 0% packet loss.
        """
        assert vm_under_test.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=30)

    @pytest.mark.polarion("CNV-12586")
    def test_seamless_in_cluster_connectivity_is_preserved_over_live_migration(self) -> None:
        """
        Test that a VM with an explicit IP address specified can preserve connectivity during live migration.

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation & cloud-init).
            - Running connectivity reference VM, with a primary UDN network.
            - Established TCP connectivity from the ref VM to the under-test VM.

        Steps:
            1. Migrate the under-test VM (and wait for completion).

        Expected:
            - The initial TCP connection is preserved (no disconnection).
        """

    test_seamless_in_cluster_connectivity_is_preserved_over_live_migration.__test__ = False

    @pytest.mark.polarion("CNV-12585")
    def test_ip_address_is_preserved_over_power_lifecycle(self) -> None:
        """
        Test that a VM with an explicit IP address specified can preserve its IP address over a power lifecycle
        (VM is stopped and started again).

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation & cloud-init).
            - The specified IP address on the under-test VM.

        Steps:
            1. Restart the under-test VM (and wait for completion).

        Expected:
            - IP address reported by VMI status and guest OS is the same as the one specified.
        """

    test_ip_address_is_preserved_over_power_lifecycle.__test__ = False
