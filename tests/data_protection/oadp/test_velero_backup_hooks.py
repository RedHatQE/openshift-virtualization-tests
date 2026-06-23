"""
Velero Backup Hook Opt-Out Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/remove-velero-hooks-stp.md
Jira: https://redhat.atlassian.net/browse/CNV-79727 # <skip-jira-utils-check>
"""

import pytest


class TestVeleroHookOptOutPausedVM:
    """
    Tests for Velero backup hook opt-out on paused VMs.

    Preconditions:
        - Running VM with per-VM opt-out annotation
        - VM paused
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16267")
    def test_backup_succeeds_with_hooks_disabled_on_paused_vm(self):
        """
        Test that backup completes without hooks on a paused VM with opt-out.

        Steps:
            1. Run Velero backup targeting the VM namespace
            2. Wait for backup to complete

        Expected:
            - Backup completes with status Completed
            - No freeze/unfreeze hooks executed during backup
        """


class TestVeleroHookOptOutBackupRestore:
    """
    Tests for full Velero backup and restore with hook opt-out.

    Preconditions:
        - Running VM with per-VM opt-out annotation disabling backup hooks
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16268")
    def test_full_backup_restore_with_hooks_disabled(self):
        """
        Test that full backup and restore workflow completes with hooks disabled.

        Steps:
            1. Run Velero backup
            2. Delete VM and namespace
            3. Restore from backup
            4. Wait for restore to complete

        Expected:
            - Backup completes successfully without hooks
            - Restore completes successfully
            - VM is running after restore
        """
