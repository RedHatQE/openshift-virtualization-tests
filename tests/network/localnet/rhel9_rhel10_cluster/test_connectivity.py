"""
Localnet Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/network.md

Markers:
    - mixed_os_nodes
"""

import pytest

__test__ = False


@pytest.mark.incremental
class TestConnectivity:
    """
    Preconditions:
        - Server VM with a secondary localnet network
        - Client VM with a secondary localnet network, running on an RHCOS 9 worker node
        - Active TCP connection established from the client VM to the server VM
    """

    @pytest.mark.polarion("CNV-15951")
    def test_connectivity_preserved_during_server_migration_to_rhcos10(self):
        """
        Test that an active TCP connection over a secondary localnet network
        is preserved when the server VM migrates from an RHCOS 9 node to an RHCOS 10 node.

        Preconditions:
            - Server VM with a secondary localnet network, running on an RHCOS 9 worker node
            - Client VM with a secondary localnet network, running on an RHCOS 9 worker node
            - Active TCP connection established from the client VM to the server VM

        Steps:
            1. Live migrate the server VM to the RHCOS 10 node

        Expected:
            - The active TCP connection from the client VM to the server VM is preserved during the migration
        """

    @pytest.mark.polarion("CNV-15966")
    def test_connectivity_preserved_during_server_migration_to_rhcos9(self):
        """
        Test that an active TCP connection over a secondary localnet network
        is preserved when the server VM migrates from an RHCOS 10 node to an RHCOS 9 node.

        Preconditions:
            - Server VM with a secondary localnet network, running on an RHCOS 10 worker node
            - Client VM with a secondary localnet network, running on an RHCOS 9 worker node
            - Active TCP connection established from the client VM to the server VM

        Steps:
            1. Live migrate the server VM to the RHCOS 9 node

        Expected:
            - The active TCP connection from the client VM to the server VM is preserved during the migration
        """
