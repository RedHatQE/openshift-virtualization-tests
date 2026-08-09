"""
Concurrent VM boot with multiple disks per VM.

Validates the ability to spin up 20 VMs simultaneously, each with 1 golden image
boot volume (PVC clone) + 1 cloud-init disk + 3 blank data volumes
(5 disk devices total in the VMI spec).

Jira: https://redhat.atlassian.net/browse/CNV-88906  # <skip-jira-utils-check>

Preconditions:
    - Fedora golden image DataSource available in openshift-virtualization-os-images
    - Storage class supporting dynamic provisioning and CSI volume cloning
    - Sufficient cluster resources to schedule 20 VMs simultaneously
"""

import pytest


@pytest.mark.tier3
@pytest.mark.conformance
@pytest.mark.polarion("CNV-16335")
def test_concurrent_vms_boot_with_four_disks():
    """
    Test that 20 VMs boot simultaneously, each reporting the expected number of disk devices.

    Preconditions:
        - 20 VMs created, each with 1 golden image boot volume, 1 cloud-init disk,
          and 3 blank data volumes
        - All 20 VMs started simultaneously and reached Running state

    Steps:
        1. For each VM, verify the number of disk devices reported in the VMI spec

    Expected:
        - All 20 VMs report 5 disk devices each in the VMI spec
    """


test_concurrent_vms_boot_with_four_disks.__test__ = False
