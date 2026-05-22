"""
Primary Network Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

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
        - Server VM connected to the primary network
        - Client VM connected to the primary network, running on an RHCOS 9 worker node
        - Ping from the client VM to the server VM succeeds
    """

    @pytest.mark.polarion("CNV-15950")
    def test_primary_connectivity_reestablished_after_server_migration_to_rhcos10(self):
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

    @pytest.mark.polarion("CNV-15967")
    def test_primary_connectivity_reestablished_after_server_migration_to_rhcos9(self):
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
