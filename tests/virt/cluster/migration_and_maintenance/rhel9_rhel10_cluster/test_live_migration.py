"""
Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/stp.md

Markers:
    - mixed_os_nodes
    - rwx_default_storage
"""

import pytest

__test__ = False


@pytest.mark.polarion("CNV-16274")
def test_vm_migrates_from_rhcos10_to_rhcos9_node():
    """
    Test that live migration from an RHCOS 10 worker node to an RHCOS 9 worker node
    completes successfully without restarting the VM.

    Preconditions:
        - Under-test VM running on an RHCOS 10 worker node

    Steps:
        1. Record guest session continuity indicator
        2. Live migrate the under-test VM to an RHCOS 9 worker node

    Expected:
        - Live migration completes successfully and the VM is running on an RHCOS 9 worker node
        - The VM did not restart during migration
    """


@pytest.mark.polarion("CNV-16275")
def test_vm_migrates_from_rhcos9_to_rhcos10_node():
    """
    Test that live migration from an RHCOS 9 worker node to an RHCOS 10 worker node
    completes successfully without restarting the VM.

    Preconditions:
        - Under-test VM running on an RHCOS 9 worker node

    Steps:
        1. Record guest session continuity indicator
        2. Live migrate the under-test VM to an RHCOS 10 worker node

    Expected:
        - Live migration completes successfully and the VM is running on an RHCOS 10 worker node
        - The VM did not restart during migration
    """
