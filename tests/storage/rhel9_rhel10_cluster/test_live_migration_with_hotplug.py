"""
Live Migration with hotplugged storage between RHCOS9 and RHCOS10 worker nodes

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md
Jira: https://redhat.atlassian.net/browse/CNV-85250 # <skip-jira-utils-check>
"""

import pytest


class TestLiveMigrationWithHotplug:
    """
    Tests for live migration with hotplugged storage volumes across RHCOS9 and RHCOS10 worker nodes.

    Markers:
        - mixed_os_nodes
        - rwx_default_storage

    Preconditions:
        - Dual-stream cluster with at least one RHCOS9 and one RHCOS10 worker node identified
        - RWX-capable storage class available
    """

    __test__ = False

    @pytest.mark.manual
    @pytest.mark.polarion("CNV-96771-1")
    def test_vm_with_hotplug_migrates_from_rhcos9_to_rhcos10(self):
        """
        Test that a VM with a hotplugged storage volume live migrates from an RHCOS9 worker node
        to an RHCOS10 worker node without data loss or corruption.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Steps:
            1. Create a VM with nodeAffinity set to an RHCOS9 worker node and wait for it to be Running
            2. Create a blank PVC
            3. Hotplug the PVC to the running VM and write test data to it
            4. Live migrate the VM (VirtualMachineInstanceMigration) to an RHCOS10 worker node
            5. Verify that the VM is running on an RHCOS10 worker node
            6. Read data from the hotplugged volume on the migrated VM

        Expected:
            - Live migration completes successfully and the VM is running on an RHCOS10 worker node
            - Data on the hotplugged volume equals the test data written before migration
        """

    @pytest.mark.manual
    @pytest.mark.polarion("CNV-96771-2")
    def test_vm_with_hotplug_migrates_from_rhcos10_to_rhcos9(self):
        """
        Test that a VM with a hotplugged storage volume live migrates from an RHCOS10 worker node
        to an RHCOS9 worker node without data loss or corruption.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Steps:
            1. Create a VM with nodeAffinity set to an RHCOS10 worker node and wait for it to be Running
            2. Create a blank PVC
            3. Hotplug the PVC to the running VM and write test data to it
            4. Live migrate the VM (VirtualMachineInstanceMigration) to an RHCOS 9 worker node
            5. Verify that the VM is running on an RHCOS9 worker node
            6. Read data from the hotplugged volume on the migrated VM

        Expected:
            - Live migration completes successfully and the VM is running on an RHCOS9 worker node
            - Data on the hotplugged volume equals the test data written before migration
        """
