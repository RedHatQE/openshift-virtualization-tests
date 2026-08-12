"""
File-Level Restore End-to-End Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest


class TestFileRestoreBackupVendorWorkflow:
    """
    End-to-end restore workflow tests simulating backup vendor integration.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
        - Backup PVC available as restore source
        - Target file content recorded before deletion (for comparison after restore)
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16767")
    def test_restore_workflow_from_api(self):
        """
        Test that the end-to-end restore workflow from request creation to file verification succeeds.

        Priority: P0

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - Backup PVC available as restore source
            - Target file content recorded before deletion (for comparison after restore)
            - Target file deleted from VM data disk (restore scenario triggered)

        Steps:
            1. Create VMFileRestore referencing the target VM and backup PVC, and the deleted file's path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check the restore resource's reported status
            4. Compare restored file content against original content
            5. Check the namespace for any temporary resources left over from the restore operation

        Expected:
            - Restored file content equals the original recorded content
            - The restore operation reports successful completion with all files accounted for in its status
            - Temporary resources created during the restore operation are cleaned up upon completion
        """
