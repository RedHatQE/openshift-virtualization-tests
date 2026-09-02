"""
Concurrent VM Boot Tests

Validates booting 20 virtual machines simultaneously, each with a multi-disk
configuration: one cloned boot volume, one cloud-init disk, and three blank
data volumes (five disk devices total in the VMI spec).

Jira: https://redhat.atlassian.net/browse/CNV-88906  # <skip-jira-utils-check>

Markers:
    - tier3
    - conformance
    - high_vm_concurrent

Preconditions:
    - Storage class supporting dynamic provisioning
    - Sufficient cluster resources to schedule 20 VMs simultaneously
"""

import pytest

from tests.storage.concurrent_vm_boot.constants import (
    NUM_BLANK_DISKS_PER_VM,
    NUM_FIXED_DISKS_PER_VM,
)

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.conformance,
    pytest.mark.high_vm_concurrent,
    pytest.mark.usefixtures("cluster_memory_for_concurrent_vms"),
]

EXPECTED_DISK_COUNT = NUM_FIXED_DISKS_PER_VM + NUM_BLANK_DISKS_PER_VM


class TestConcurrentVMBoot:
    """Tests for booting multiple VMs simultaneously with multi-disk configurations.

    Preconditions:
        - Fedora golden image DataSource available in the openshift-virtualization-os-images namespace
        - Storage class supporting dynamic provisioning and CSI volume cloning
        - Sufficient cluster resources to schedule 20 VMs simultaneously
    """

    @pytest.mark.polarion("CNV-16335")
    def test_concurrent_vms_boot_with_five_disks(self, running_vms_with_five_disks):
        """
        Test that 20 VMs boot simultaneously with five disk devices each and all reach Running state.

        Preconditions:
            - 20 running VMs, each with one golden image boot volume (PVC clone via DataSource),
              one cloud-init disk, and three blank data volumes

        Steps:
            1. For each VM, query the disk devices reported in the VMI spec

        Expected:
            - All 20 VMs report exactly five disk devices each in the VMI spec
        """
        disk_failures = []
        for vm in running_vms_with_five_disks:
            actual_count = len(vm.vmi.instance.spec.domain.devices.disks)
            if actual_count != EXPECTED_DISK_COUNT:
                disk_failures.append(f"VM {vm.name} has {actual_count} disks, expected {EXPECTED_DISK_COUNT}")
        assert not disk_failures, "\n".join(disk_failures)
