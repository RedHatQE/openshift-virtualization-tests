"""
Concurrent VM boot with multiple disks per VM.

Validates the ability to spin up multiple VMs simultaneously, each with
1 golden image boot volume (PVC clone) + 1 cloud-init disk + 3 blank data volumes
(5 disk devices total in the VMI spec).

Jira: https://redhat.atlassian.net/browse/CNV-88906  # <skip-jira-utils-check>

Preconditions:
    - Fedora golden image DataSource available in openshift-virtualization-os-images
    - Storage class supporting dynamic provisioning and CSI volume cloning
    - Sufficient cluster resources to schedule multiple VMs simultaneously
"""

import pytest

from tests.storage.concurrent_vm_boot.constants import NUM_BLANK_DISKS_PER_VM, NUM_CONCURRENT_VMS

pytestmark = [pytest.mark.tier3, pytest.mark.conformance]

# 1 golden image boot disk + 1 cloud-init disk + NUM_BLANK_DISKS_PER_VM blank DVs
EXPECTED_DISK_COUNT = 2 + NUM_BLANK_DISKS_PER_VM


@pytest.mark.polarion("CNV-16335")
def test_concurrent_vms_boot_with_four_disks(
    running_vms_with_four_disks,
):
    """
    Test that 20 VMs boot simultaneously, each with the expected disk count.

    Preconditions:
        - NUM_CONCURRENT_VMS VMs created, each with 1 golden image boot + 3 blank DVs
        - All VMs started simultaneously and reached Running state

    Steps:
        1. Verify all VMs reached Running state
        2. For each VM, verify the disk count from the VMI spec

    Expected:
        - All NUM_CONCURRENT_VMS VMs are running with EXPECTED_DISK_COUNT disks each
    """
    assert len(running_vms_with_four_disks) == NUM_CONCURRENT_VMS, (
        f"Expected {NUM_CONCURRENT_VMS} running VMs, got {len(running_vms_with_four_disks)}"
    )
    for vm in running_vms_with_four_disks:
        vm_disks = vm.vmi.instance.spec.domain.devices.disks
        assert len(vm_disks) == EXPECTED_DISK_COUNT, (
            f"VM {vm.name} has {len(vm_disks)} disks, expected {EXPECTED_DISK_COUNT}"
        )
