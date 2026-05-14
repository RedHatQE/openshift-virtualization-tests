"""
Linux Bridge Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/network.md

Markers:
    - mixed_os_nodes
"""

import ipaddress

import pytest

from libs.net.traffic_generator import is_tcp_connection
from libs.vm.affinity import new_node_affinity
from tests.network.l2_bridge.libl2bridge import RHCOS9_WORKER_LABEL
from utilities.virt import migrate_vm_and_verify


@pytest.mark.mixed_os_nodes
@pytest.mark.incremental
class TestConnectivity:
    """
    Preconditions:
        - Server VM with a secondary Linux bridge network
        - Client VM with a secondary Linux bridge network, running on an RHCOS 9 worker node
        - Active TCP connection established from the client VM to the server VM
    """

    @pytest.mark.polarion("CNV-15949")
    def test_linux_bridge_connectivity_preserved_during_server_migration_to_rhcos10(
        self,
        subtests,
        bridge_running_vms,
        bridge_active_tcp_connections,
    ):
        """
        Test that an active TCP connection over a secondary Linux bridge network
        is preserved when the server VM migrates from an RHCOS 9 node to an RHCOS 10 node.

        Preconditions:
            - Server VM with a secondary Linux bridge network, running on an RHCOS 9 worker node
            - Client VM with a secondary Linux bridge network, running on an RHCOS 9 worker node
            - Active TCP connection established from the client VM to the server VM

        Steps:
            1. Live migrate the server VM to the RHCOS 10 node

        Expected:
            - The active TCP connection from the client VM to the server VM is preserved during the migration
        """
        server_vm, _ = bridge_running_vms
        server_vm.set_template_affinity(affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=False))
        migrate_vm_and_verify(vm=server_vm)
        for client, server in bridge_active_tcp_connections:
            with subtests.test(msg=f"IPv{ipaddress.ip_address(client.server_ip).version} after migration to RHCOS 10"):
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection lost after migrating {server_vm.name} to RHCOS 10 node"
                )

    @pytest.mark.polarion("CNV-15964")
    def test_linux_bridge_connectivity_preserved_during_server_migration_to_rhcos9(
        self,
        subtests,
        bridge_running_vms,
        bridge_active_tcp_connections,
    ):
        """
        Test that an active TCP connection over a secondary Linux bridge network
        is preserved when the server VM migrates from an RHCOS 10 node to an RHCOS 9 node.

        Preconditions:
            - Server VM with a secondary Linux bridge network, running on an RHCOS 10 worker node
            - Client VM with a secondary Linux bridge network, running on an RHCOS 9 worker node
            - Active TCP connection established from the client VM to the server VM

        Steps:
            1. Live migrate the server VM to the RHCOS 9 node

        Expected:
            - The active TCP connection from the client VM to the server VM is preserved during the migration
        """
        server_vm, _ = bridge_running_vms
        server_vm.set_template_affinity(affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True))
        migrate_vm_and_verify(vm=server_vm)
        for client, server in bridge_active_tcp_connections:
            with subtests.test(
                msg=f"IPv{ipaddress.ip_address(client.server_ip).version} after migration back to RHCOS 9"
            ):
                assert is_tcp_connection(server=server, client=client), (
                    f"TCP connection lost after migrating {server_vm.name} back to RHCOS 9 node"
                )
