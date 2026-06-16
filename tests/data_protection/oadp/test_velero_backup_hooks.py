"""
Velero Backup Hook Opt-Out Tests

STP Reference:
Jira: CNV-79727
"""

import pytest


class TestVeleroBackupHookOptOut:
    """
    Tests for Velero backup hook opt-out with paused VMs and full backup/restore.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/116

    Preconditions:
        - OADP operator installed and configured
        - Velero configured with default backup storage location
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16267")
    def test_backup_paused_vm_hooks_disabled(self):
        """
        Test that Velero backup of a paused VM completes with hooks disabled.

        Preconditions:
            - VM deployed with kubevirt.io/skip-backup-hooks: "true"

        Steps:
            1. Pause the running VM
            2. Run Velero backup targeting the VM namespace
            3. Check Velero backup logs for hook execution entries

        Expected:
            - Backup logs do not contain freeze/unfreeze hook entries
        """

    @pytest.mark.polarion("CNV-16268")
    def test_full_backup_restore_hooks_disabled(self):
        """
        Test that full Velero backup and restore completes with hooks disabled.

        Preconditions:
            - Running VM deployed with kubevirt.io/skip-backup-hooks: "true"

        Steps:
            1. Run Velero backup targeting the VM namespace
            2. Delete the VM and its namespace
            3. Restore from backup
            4. Wait for VM to reach Running state

        Expected:
            - VM is Running
        """

    @pytest.mark.polarion("CNV-16269")
    def test_backup_paused_vm_default_hooks(self):
        """
        Test that Velero backup of a paused VM attempts hooks by default.

        Preconditions:
            - VM deployed without opt-out annotation

        Steps:
            1. Pause the running VM
            2. Run Velero backup targeting the VM namespace
            3. Check Velero backup logs for hook execution entries

        Expected:
            - Backup logs contain freeze/unfreeze hook entries
        """
