"""
Migration Metrics on a Dual-Stream (RHCOS 9 + RHCOS 10) Cluster

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

Markers:
    - mixed_os_nodes
    - rwx_default_storage

Preconditions:
    - Migration bandwidth limited for the under-test VM, so migration metrics are sampled while migration is in progress
"""

import pytest

__test__ = False

pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.rwx_default_storage,
]


@pytest.mark.polarion("CNV-16823")
def test_migration_metrics_reported_rhcos9_to_rhcos10():
    """
    Test that migration metrics are reported when a VM is live migrated from an RHCOS 9 worker node
    to an RHCOS 10 worker node.

    Preconditions:
        - Migratable VM running on an RHCOS 9 worker node

    Steps:
        1. Live migrate the VM to an RHCOS 10 worker node
        2. Query the migration duration, data processed, and bandwidth metrics for the under-test VM

    Expected:
        - Migration duration metric value is greater than zero
        - Migration data processed metric value is greater than zero
        - Migration bandwidth metric value is greater than zero
    """


@pytest.mark.polarion("CNV-16824")
def test_migration_metrics_reported_rhcos10_to_rhcos9():
    """
    Test that migration metrics are reported when a VM is live migrated from an RHCOS 10 worker node
    to an RHCOS 9 worker node.

    Preconditions:
        - Migratable VM running on an RHCOS 10 worker node

    Steps:
        1. Live migrate the VM to an RHCOS 9 worker node
        2. Query the migration duration, data processed, and bandwidth metrics for the under-test VM

    Expected:
        - Migration duration metric value is greater than zero
        - Migration data processed metric value is greater than zero
        - Migration bandwidth metric value is greater than zero
    """
