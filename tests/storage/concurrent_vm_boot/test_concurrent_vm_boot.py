"""
Concurrent VM Boot Tests

Validates booting 20 virtual machines simultaneously, each with a multi-disk
configuration: one cloned boot volume, one cloud-init disk, and three blank
data volumes (five disk devices total in the VMI spec).

Jira: https://redhat.atlassian.net/browse/CNV-88906  # <skip-jira-utils-check>

Markers:
    - tier3
    - conformance
"""

import pytest

__test__ = False

pytestmark = [pytest.mark.tier3, pytest.mark.conformance]


class TestConcurrentVMBoot:
    """
    Tests for booting multiple VMs simultaneously with multi-disk configurations.

    Preconditions:
        - Fedora golden image DataSource available in the openshift-virtualization-os-images namespace
        - All schedulable worker nodes share the same architecture as the golden image
        - Storage class supporting dynamic provisioning and CSI volume cloning
        - Sufficient cluster resources to schedule 20 VMs simultaneously
    """

    @pytest.mark.polarion("CNV-16335")
    def test_concurrent_vms_boot_with_five_disks(self):
        """
        Test that 20 VMs boot simultaneously with five disk devices each and all reach Running state.

        Preconditions:
            - Fedora golden image DataSource available in the openshift-virtualization-os-images namespace
            - All schedulable worker nodes share the same architecture as the golden image
            - Storage class supporting dynamic provisioning and CSI volume cloning
            - Sufficient cluster resources to schedule 20 VMs simultaneously
            - 20 VMs created, each with one golden image boot volume (PVC clone via DataSource),
              one cloud-init disk, and three blank data volumes
            - All 20 VMs started simultaneously and reached Running state

        Steps:
            1. Create 20 VMs, each with one golden image boot volume (PVC clone via DataSource),
               one cloud-init disk, and three blank data volumes
            2. Start all 20 VMs simultaneously
            3. Wait for all 20 VMs to reach Running state
            4. For each VM, inspect the disk devices reported in the VMI spec

        Expected:
            - All 20 VMs report exactly five disk devices each in the VMI spec
        """
