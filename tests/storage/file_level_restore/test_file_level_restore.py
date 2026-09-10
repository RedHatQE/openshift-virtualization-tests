"""
File-Level Restore Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest


class TestFileRestoreOperatorDeployment:
    """
    Tests for vm-file-restore-operator deployment via HCO-managed lifecycle.

    Preconditions:
        - OpenShift Virtualization installed via HyperConverged CR (HCO-managed lifecycle)
        - openshift-cnv namespace exists
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16810")
    def test_file_restore_operator_deployed_after_cnv_install(self):
        """
        Test that vm-file-restore-operator is deployed and running after OpenShift Virtualization
        installation via HCO-managed lifecycle.

        Preconditions:
            - OpenShift Virtualization installed via HyperConverged CR (HCO-managed lifecycle)
            - openshift-cnv namespace exists

        Steps:
            1. Verify vm-file-restore-operator deployment exists in openshift-cnv namespace
            2. Verify vm-file-restore-operator pod is Running

        Expected:
            - vm-file-restore-operator deployment exists and its pod is Running
        """


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

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - Backup PVC available as restore source
            - Target file content recorded before deletion (for comparison after restore)
            - Target file deleted from VM data disk (restore scenario triggered)

        Steps:
            1. Create VMFileRestore referencing the target VM and backup PVC, and the deleted file's path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Review the restore operation status for transferred file accounting and error reporting
            4. Compare restored file content against original content
            5. Check the namespace for any temporary resources left over from the restore operation

        Expected:
            - Restored file content equals the original recorded content
            - The restore status reports a restored-file count equal to the number of files requested for restore
            - Temporary resources created during the restore operation are cleaned up upon completion
        """


class TestFileRestoreWindowsGuestFileCount:
    """
    Tests for file count reporting accuracy on Windows VM guests.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
        - Backup volume (PVC or VolumeSnapshot) with a known number of files on NTFS filesystem
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16770")
    def test_file_count_matches_transferred_on_windows_vm(self):
        """
        Test that the restored file count in status matches actual files transferred on a Windows VM.

        Preconditions:
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - Backup volume (PVC or VolumeSnapshot) containing a known number of NTFS files
            - Target files deleted from the Windows VM data disk

        Steps:
            1. Create VMFileRestore for the backup volume with a known number of files
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check the file count reported by the restore resource
            4. Count the restored files inside the Windows VM

        Expected:
            - File count in VMFileRestore status equals the actual number of files restored in the Windows VM
        """


class TestFileRestoreWindowsNTFSACLsAndOwnership:
    """
    Tests for NTFS ACLs and ownership preservation on Windows VM file restore.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16768")
    def test_windows_vm_restore_from_backup_pvc_preserves_ntfs_acls_and_ownership(self):
        """
        Test that file restore on Windows VM from a backup PVC preserves NTFS ACLs and ownership.

        Preconditions:
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - NTFS backup PVC with files having known ACLs and owner SID recorded
            - Target file deleted from the Windows VM data disk

        Steps:
            1. Create VMFileRestore from Windows NTFS backup PVC
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Verify NTFS ACL entries and owner information on the restored file inside the Windows VM

        Expected:
            - NTFS ACL entries on the restored file match the recorded baseline
            - Owner SID on the restored file matches the recorded baseline
        """

    @pytest.mark.polarion("CNV-16769")
    def test_windows_vm_restore_from_snapshot_preserves_ntfs_acls_and_ownership(self):
        """
        Test that file restore on Windows VM from a volume snapshot preserves NTFS ACLs and ownership.

        Preconditions:
            - VolumeSnapshot-capable StorageClass available
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - VolumeSnapshot of Windows NTFS data disk with files having known ACLs and owner SID recorded
            - Target file deleted from the Windows VM data disk

        Steps:
            1. Create VMFileRestore from Windows NTFS VolumeSnapshot
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Verify NTFS ACL entries and owner information on the restored file inside the Windows VM

        Expected:
            - NTFS ACL entries on the restored file match the snapshot baseline
            - Owner SID on the restored file matches the snapshot baseline
        """


class TestFileRestoreWindowsDriveRoot:
    """
    Tests for Windows file restore from drive root paths.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
        - Backup volume with a file at a Windows drive root path
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16771")
    def test_windows_vm_restore_from_drive_root_path(self):
        """
        Test that file restore on Windows VM succeeds when the source file is at a drive root.

        Preconditions:
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - Backup volume containing a file at a Windows drive root path with known content
            - Target file deleted from the Windows VM

        Steps:
            1. Create VMFileRestore with a drive-root source path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Read the restored file content inside the Windows VM and compare with source

        Expected:
            - Restored file content matches the source
        """


class TestFileRestoreRootDiskToOriginalPath:
    """
    Tests for restoring files from root disk backup to their original location on a running Linux VM.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16811")
    def test_restore_from_root_disk_snapshot_to_original_path(self):
        """
        Test that files are restored from a root disk VolumeSnapshot to their original location
        in a running Linux VM.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - VolumeSnapshot of VM root disk marked readyToUse=true
            - Target file original content recorded before deletion

        Steps:
            1. Delete target file from running VM to simulate data loss
            2. Create VMFileRestore from root disk VolumeSnapshot targeting the original file path
            3. Wait for VMFileRestore to reach Succeeded phase
            4. Compare restored file content against the recorded original

        Expected:
            - Restored file content matches the recorded original
            - File is restored to its original path on the running Linux VM
        """

    @pytest.mark.polarion("CNV-16812")
    def test_restore_from_root_disk_backup_pvc_to_original_path(self):
        """
        Test that files are restored from a root disk backup PVC to their original location
        in a running Linux VM.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - Backup PVC cloned from the VM root disk PVC
            - Target file original content recorded before deletion

        Steps:
            1. Delete target file from running VM to simulate data loss
            2. Create VMFileRestore from root disk backup PVC targeting the original file path
            3. Wait for VMFileRestore to reach Succeeded phase
            4. Compare restored file content against the recorded original

        Expected:
            - Restored file content matches the recorded original
            - File is restored to its original path on the running Linux VM
        """


class TestFileRestoreSequentialFromSameSnapshot:
    """
    Tests for data disk VolumeSnapshot restore and sequential restore from the same snapshot.

    Markers:
        - incremental

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
        - VM data disk with two distinct test files
        - VolumeSnapshot of the VM data disk with both test files available
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16813")
    def test_restore_from_data_disk_snapshot(self):
        """
        Test that files are restored from a data disk VolumeSnapshot in a running Linux VM
        and temporary resources are cleaned up after the operation.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - VolumeSnapshot of the VM data disk with two distinct test files available
            - Original content recorded for the first target file before deletion

        Steps:
            1. Delete the first target file from the VM data disk
            2. Create VMFileRestore from the data disk VolumeSnapshot targeting the deleted file path
            3. Wait for VMFileRestore to reach Succeeded phase
            4. Check the namespace for temporary resources left over from the restore operation
            5. Compare restored file content against the recorded original

        Expected:
            - Restore operation from the data disk VolumeSnapshot reaches Succeeded phase
            - Restored file content matches the recorded original
            - Temporary resources from the operation are cleaned up
        """

    @pytest.mark.polarion("CNV-16815")
    def test_second_restore_from_same_data_disk_snapshot(self):
        """
        Test that a second restore from the same data disk VolumeSnapshot completes successfully.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - VolumeSnapshot of the VM data disk with two distinct test files available
            - Restore from the data disk VolumeSnapshot completed successfully
            - Original content recorded for the second target file before deletion

        Steps:
            1. Delete the second target file from the VM data disk
            2. Create a second VMFileRestore from the same data disk VolumeSnapshot targeting the deleted file path
            3. Wait for VMFileRestore to reach Succeeded phase
            4. Compare restored file content against the recorded original

        Expected:
            - Second restore operation from the same data disk VolumeSnapshot reaches Succeeded phase
            - Restored file content matches the recorded original
        """
