"""
Primary Network Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/network.md

Markers:
    - mixed_os_nodes
"""

import pytest

from libs.net.vmspec import lookup_iface_status
from libs.vm.affinity import new_node_affinity
from tests.network.libs.connectivity import build_ping_command
from utilities.constants.cluster import RHCOS9_WORKER_LABEL
from utilities.virt import migrate_vm_and_verify


@pytest.mark.mixed_os_nodes
@pytest.mark.incremental
@pytest.mark.usefixtures("primary_network_connectivity")
class TestConnectivity:
    """
    Preconditions:
        - Server VM connected to the primary network
        - Client VM connected to the primary network, running on an RHCOS 9 worker node
        - Ping from the client VM to the server VM succeeds
    """

    @pytest.mark.polarion("CNV-15950")
    def test_primary_connectivity_reestablished_after_server_migration_to_rhcos10(
        self,
        subtests,
        admin_client,
        primary_client_vm,
        primary_server_vm,
    ):
        """
        Test that network connectivity over the primary network can be re-established after
        the server VM migrates from an RHCOS 9 node to an RHCOS 10 node.

        Preconditions:
            - Server VM connected to the primary network, running on an RHCOS 9 worker node
            - Client VM connected to the primary network, running on an RHCOS 9 worker node
            - Ping from the client VM to the server VM succeeds

        Steps:
            1. Live migrate the server VM to the RHCOS 10 node

        Expected:
            - Ping from the client VM to the server VM succeeds after the migration
        """
        primary_iface_name = primary_server_vm.vmi.interfaces[0].name
        primary_server_vm.set_template_affinity(affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=False))
        migrate_vm_and_verify(vm=primary_server_vm, client=admin_client)
        for ip in lookup_iface_status(vm=primary_server_vm, iface_name=primary_iface_name)["ipAddresses"]:
            with subtests.test(msg=f"Testing {primary_server_vm.name} IP address: {ip}"):
                primary_client_vm.console(
                    commands=[build_ping_command(dst_ip=ip, count=10, timeout=10)],
                    timeout=20,
                )

    @pytest.mark.polarion("CNV-15967")
    def test_primary_connectivity_reestablished_after_server_migration_to_rhcos9(
        self,
        subtests,
        admin_client,
        primary_client_vm,
        primary_server_vm,
    ):
        """
        Test that network connectivity over the primary network can be re-established after
        the server VM migrates from an RHCOS 10 node to an RHCOS 9 node.

        Preconditions:
            - Server VM connected to the primary network, running on an RHCOS 10 worker node
            - Client VM connected to the primary network, running on an RHCOS 9 worker node
            - Ping from the client VM to the server VM succeeds

        Steps:
            1. Live migrate the server VM to the RHCOS 9 node

        Expected:
            - Ping from the client VM to the server VM succeeds after the migration
        """
        primary_iface_name = primary_server_vm.vmi.interfaces[0].name
        primary_server_vm.set_template_affinity(affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True))
        migrate_vm_and_verify(vm=primary_server_vm, client=admin_client)
        for ip in lookup_iface_status(vm=primary_server_vm, iface_name=primary_iface_name)["ipAddresses"]:
            with subtests.test(msg=f"Testing {primary_server_vm.name} IP address: {ip}"):
                primary_client_vm.console(
                    commands=[build_ping_command(dst_ip=ip, count=10, timeout=10)],
                    timeout=20,
                )
