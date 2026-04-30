"""
Primary Network Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/network.md

Markers:
    - dual_stream
"""

import pytest

__test__ = False


@pytest.mark.polarion("CNV-15950")
def test_connectivity_preserved_during_server_migration():
    """
    Test that primary network connectivity is preserved when the server VM migrates
    between RHCOS 9 and RHCOS 10 nodes.

    Preconditions:
        - Server VM connected to the primary network, running on an RHCOS 9 worker node via node selector
        - Client VM connected to the primary network, running on an RHCOS 9 worker node via node selector
        - Ping from the client VM to the server VM succeeds

    Steps:
        1. Live migrate the server VM to the RHCOS 10 node
        2. Live migrate the server VM back to the RHCOS 9 node

    Expected:
        - Ping from the client VM to the server VM succeeds after each migration
    """
