"""
Velero Backup Hook Opt-Out Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/remove-velero-hooks-stp.md
Jira: https://redhat.atlassian.net/browse/CNV-79727 # <skip-jira-utils-check>
"""

import pytest


class TestVeleroBackupHookOptOut:
    """
    Tests for Velero backup hook opt-out with backup/restore operations.

    Preconditions:
        - VM with backup hooks disabled
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16267")
    def test_backup_paused_vm_hooks_disabled(self):
        """
        Test that backup of paused VM completes with hooks disabled.

        Preconditions:
            - VM with backup hooks disabled, paused

        Steps:
            1. Run Velero backup

        Expected:
            Backup completes successfully without freeze/unfreeze hook execution
        """

    @pytest.mark.polarion("CNV-16268")
    def test_full_backup_restore_hooks_disabled(self):
        """
        Test that full backup/restore cycle completes with hooks disabled.

        Preconditions:
            - Running VM with backup hooks disabled

        Steps:
            1. Run Velero backup
            2. Delete VM and namespace
            3. Restore from backup

        Expected:
            VM is restored and running after backup/restore cycle
        """
