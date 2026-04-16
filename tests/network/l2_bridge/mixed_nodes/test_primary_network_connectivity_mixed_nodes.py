"""
Primary Network Connectivity After Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/65

Markers:
    - special_infra

Preconditions:
    - Target VM connected to the primary network, running on an RHCOS 9 worker node
    - Source VM connected to the primary network, running on an RHCOS 9 worker node
"""

import pytest

__test__ = False


@pytest.mark.polarion("CNV-0")
def test_connectivity_over_primary_network_preserved_during_source_migration():
    """
    Test that primary network connectivity is preserved when the source VM migrates
    between RHCOS 9 and RHCOS 10 nodes.

    Preconditions:
        - Target VM connected to the primary network, running on an RHCOS 9 worker node
        - Source VM connected to the primary network, running on an RHCOS 9 worker node

    Steps:
        1. Update source VM node selector to target the RHCOS 10 node
        2. Live migrate the source VM from the RHCOS 9 node to the RHCOS 10 node
        3. Wait for migration to complete
        4. Ping the target VM from the source VM
        5. Update source VM node selector to target the RHCOS 9 node
        6. Live migrate the source VM from the RHCOS 10 node back to the RHCOS 9 node
        7. Wait for migration to complete
        8. Ping the target VM from the source VM

    Expected:
        - Ping succeeds after each migration
    """


@pytest.mark.polarion("CNV-2")
def test_connectivity_over_primary_network_preserved_during_target_migration():
    """
    Test that primary network connectivity is preserved when the target VM migrates
    between RHCOS 9 and RHCOS 10 nodes.

    Preconditions:
        - Target VM connected to the primary network, running on an RHCOS 9 worker node
        - Source VM connected to the primary network, running on an RHCOS 9 worker node

    Steps:
        1. Update target VM node selector to target the RHCOS 10 node
        2. Live migrate the target VM from the RHCOS 9 node to the RHCOS 10 node
        3. Wait for migration to complete
        4. Ping the target VM from the source VM
        5. Update target VM node selector to target the RHCOS 9 node
        6. Live migrate the target VM from the RHCOS 10 node back to the RHCOS 9 node
        7. Wait for migration to complete
        8. Ping the target VM from the source VM

    Expected:
        - Ping succeeds after each migration
    """
