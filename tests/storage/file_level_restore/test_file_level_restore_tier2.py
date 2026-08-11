"""
File-Level Restore End-to-End Tests

Python Tier 2 P0 scenarios only; remaining Tier 2 priorities are follow-up work.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest


class TestFileRestoreBackupVendorWorkflow:
    """
    End-to-end restore workflow tests simulating backup vendor integration.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
        - VolumeSnapshot of VM data disk available as backup source
        - Target file content recorded before deletion (for comparison after restore)
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16767")
    def test_restore_workflow_from_api(self):
        """
        Test that the end-to-end restore workflow from request creation to file verification succeeds.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - Target file deleted from VM data disk after snapshot taken (restore scenario triggered)

        Steps:
            1. Create VMFileRestore via the API referencing the target VM and VolumeSnapshot backup
            2. Monitor phase progression through the restore state machine
            3. Wait for VMFileRestore to reach Succeeded phase
            4. Compare restored file content against original content
            5. Read VMFileRestore status fields (phase, fileCount, conditions)
            6. List operator-created PVCs in the namespace

        Expected:
            - Restored file content equals the original recorded content
            - status.phase equals Succeeded and status.fileCount is greater than or equal to 1
            - No operator-created temporary PVCs remain in the namespace
        """
