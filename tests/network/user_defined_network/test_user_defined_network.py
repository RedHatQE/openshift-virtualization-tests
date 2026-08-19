from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

import pytest
from ocp_resources.utils.constants import TIMEOUT_1MINUTE

from libs.net.traffic_generator import is_tcp_connection
from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from tests.network.user_defined_network.libudn import lookup_default_pod_ip
from utilities.constants.networking import PUBLIC_DNS_SERVER_IP
from utilities.constants.pytest import QUARANTINED
from utilities.constants.timeouts import TIMEOUT_1MIN
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

    from libs.net.traffic_generator import TcpServer, VMTcpClient
    from libs.vm.vm import BaseVirtualMachine


@pytest.mark.ipv4
@pytest.mark.s390x
@pytest.mark.single_nic
class TestPrimaryUdn:
    """
    Tests for a VM connected to a primary user-defined network (UDN).

    Preconditions:
        - UDN namespace (with UDN annotation) with KubeMacPool enabled.
        - Primary UDN resource with an IP range defined.
        - Running under-test VM attached to the primary UDN network.
    """

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

    @pytest.mark.polarion("CNV-11432")
    def test_vm_to_pod_connectivity_on_udn(self, vma_udn, udn_pod):
        """
        Test that a VM reaches a pod on the same primary UDN network (east-west connectivity).

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

        Preconditions:
            - Running under-test VM attached to the primary UDN network.
            - Running reference pod attached to the same primary UDN network.

        Steps:
            1. Get the reference pod IP address, allocated from the UDN subnet.
            2. Execute a ping command from the under-test VM to the reference pod IP address
               over the primary UDN interface.

        Expected:
            - Ping succeeds with 0% packet loss.
        """
        pod_ip = lookup_default_pod_ip(pod=udn_pod)
        vma_udn.console(commands=[f"ping -c 3 {pod_ip}"], timeout=TIMEOUT_1MIN)

    @pytest.mark.polarion("CNV-11462")
    def test_tcp_connectivity_via_cluster_ip_service_on_primary_udn(self):
        """
        Test that a VM's primary UDN interface is reachable through a ClusterIP service.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

        Preconditions:
            - Running server VM attached to the primary UDN network.
            - ClusterIP service targeting the server VM primary UDN interface.
            - Running client VM attached to the same primary UDN network.

        Steps:
            1. Start a TCP server on the server VM.
            2. Establish a TCP connection from the client VM to the ClusterIP service address.

        Expected:
            - The TCP connection to the server VM through the ClusterIP service succeeds.
        """

    test_tcp_connectivity_via_cluster_ip_service_on_primary_udn.__test__ = False

    @pytest.mark.polarion("CNV-16773")
    def test_kubemacpool_assigns_mac_on_primary_udn_interface(self):
        """
        Test that KubeMacPool assigns a MAC address from its pool to a VM's primary UDN interface.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

        Preconditions:
            - Running under-test VM attached to the primary UDN network.

        Steps:
            1. Read the MAC address assigned to the VM primary UDN interface from the VM object.

        Expected:
            - The primary UDN interface MAC address is within the KubeMacPool range.
        """

    test_kubemacpool_assigns_mac_on_primary_udn_interface.__test__ = False

    @pytest.mark.polarion("CNV-11435")
    def test_network_policy_enforcement_on_primary_udn_interface(self):
        """
        Test that a network policy is enforced on the VM primary UDN interface: traffic from
        an allowed pod is permitted while traffic from a denied pod is blocked.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

        Preconditions:
            - Running under-test VM attached to the primary UDN network.
            - Running allowed pod attached to the primary UDN network.
            - Running denied pod attached to the primary UDN network.
            - Network policy applied to the primary UDN, allowing traffic from an allowed pod
              and denying traffic from a denied pod.

        Steps:
            1. Execute a ping command from the allowed pod to the under-test VM
               primary UDN interface IP address.
            2. Execute a ping command from the denied pod to the under-test VM
               primary UDN interface IP address.

        Expected:
            - Ping from the allowed pod succeeds with 0% packet loss.
            - Ping from the denied pod fails with 100% packet loss.
        """

    test_network_policy_enforcement_on_primary_udn_interface.__test__ = False

    @pytest.mark.order("last")
    @pytest.mark.usefixtures("vma_udn")
    @pytest.mark.polarion("CNV-11451")
    def test_udn_cannot_be_deleted_while_vm_connected(
        self, namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork
    ):
        """
        [NEGATIVE] Test that a primary UDN cannot be removed while a VM is connected to it.

        This test runs last since it issues a DELETE against the primary UDN shared by the other
        tests. If deletion protection is broken (a bug), running it earlier would remove that
        network and break the tests sharing it.

        No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

        Preconditions:
            - Running under-test VM attached to the primary UDN network.

        Steps:
            1. Attempt to delete the primary UDN resource.

        Expected:
            - The primary UDN resource still exists (deletion is blocked while the VM is connected).
        """
        assert not namespaced_layer2_user_defined_network.delete(wait=True, timeout=20), (
            "UDN was deleted despite having a connected VM."
        )
