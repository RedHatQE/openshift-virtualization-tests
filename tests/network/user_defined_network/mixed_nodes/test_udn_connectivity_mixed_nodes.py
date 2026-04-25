"""
Primary UDN Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/65

Markers:
    - special_infra

Preconditions:
    - Primary User Defined Network created
    - Server VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
    - Client VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
    - Active TCP connection established from the client VM to the server VM
"""

import pytest

__test__ = False


@pytest.mark.polarion("CNV-0")
def test_connectivity_over_udn_preserved_during_client_migration():
    """
    Test that TCP connectivity is preserved when the client VM migrates
    between RHCOS 9 and RHCOS 10 nodes.

    Preconditions:
        - Primary User Defined Network created
        - Server VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
        - Client VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
        - Active TCP connection established from the client VM to the server VM

    Steps:
        1. Update client VM node selector to target the RHCOS 10 node
        2. Live migrate the client VM from the RHCOS 9 node to the RHCOS 10 node
        3. Wait for migration to complete
        4. Verify TCP connectivity from the client VM to the server VM
        5. Update client VM node selector to target the RHCOS 9 node
        6. Live migrate the client VM from the RHCOS 10 node back to the RHCOS 9 node
        7. Wait for migration to complete
        8. Verify TCP connectivity from the client VM to the server VM

    Expected:
        - TCP connection from the client VM to the server VM succeeds after each migration
    """


@pytest.mark.polarion("CNV-4")
def test_connectivity_over_udn_preserved_during_server_migration():
    """
    Test that TCP connectivity is preserved when the server VM migrates
    between RHCOS 9 and RHCOS 10 nodes.

    Preconditions:
        - Primary User Defined Network created
        - Server VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
        - Client VM connected to a primary User Defined Network, running on an RHCOS 9 worker node
        - Active TCP connection established from the client VM to the server VM

    Steps:
        1. Update server VM node selector to target the RHCOS 10 node
        2. Live migrate the server VM from the RHCOS 9 node to the RHCOS 10 node
        3. Wait for migration to complete
        4. Verify TCP connectivity from the client VM to the server VM
        5. Update server VM node selector to target the RHCOS 9 node
        6. Live migrate the server VM from the RHCOS 10 node back to the RHCOS 9 node
        7. Wait for migration to complete
        8. Verify TCP connectivity from the client VM to the server VM

    Expected:
        - TCP connection from the client VM to the server VM succeeds after each migration
    """
