"""
File-Level Restore Windows Guest Tests

Python Tier 3 P0 scenarios only; remaining Tier 3 priorities are follow-up work.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest


@pytest.mark.tier3
@pytest.mark.windows
class TestFileRestoreWindowsGuestFileCount:
    """
    Tests for file count reporting accuracy on Windows VM guests.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server installed
        - filerestore user configured in Windows VM with operator SSH public key
        - Backup volume with a known number of files on NTFS filesystem
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16770")
    def test_file_count_matches_transferred_on_windows_vm(self):
        """
        Test that the restored file count in status matches actual files transferred on a Windows VM.

        Preconditions:
            - Running Windows VM with guest helper installed and filerestore user SSH-configured
            - Backup PVC containing a known NTFS files

        Steps:
            1. Create VMFileRestore requesting a known number of Windows files
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Read status.fileCount from the VMFileRestore resource
            4. Count files at target paths inside the Windows VM

        Expected:
            - File count in VMFileRestore status equals the actual number of files restored in the Windows VM
        """


@pytest.mark.tier3
@pytest.mark.windows
class TestFileRestoreWindowsNTFSMetadata:
    """
    Tests for NTFS metadata preservation on Windows VM file restore.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and filerestore user configured
        - Backup volumes with NTFS files having known ACLs and owner SID recorded (icacls + Get-Acl baseline)
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16768")
    def test_windows_vm_restore_from_backup_pvc_preserves_ntfs_metadata(self):
        """
        Test that file restore on Windows VM from a backup PVC preserves NTFS metadata and ACLs.

        Preconditions:
            - Running Windows VM with guest helper installed
            - NTFS backup PVC with files having known ACLs and owner SID recorded

        Steps:
            1. Create VMFileRestore from Windows NTFS backup PVC
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Run icacls and Get-Acl on the restored file inside the Windows VM

        Expected:
            - NTFS ACL entries on the restored file match the recorded baseline
            - Owner SID on the restored file matches the recorded baseline
        """

    @pytest.mark.polarion("CNV-16769")
    def test_windows_vm_restore_from_snapshot_preserves_ntfs_metadata(self):
        """
        Test that file restore on Windows VM from a volume snapshot preserves NTFS metadata and ACLs.

        Preconditions:
            - Running Windows VM with guest helper installed
            - VolumeSnapshot of Windows NTFS data disk with files having known ACLs and owner SID recorded

        Steps:
            1. Create VMFileRestore from Windows NTFS VolumeSnapshot
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Run icacls and Get-Acl on the restored file inside the Windows VM

        Expected:
            - NTFS ACL entries on the restored file match the snapshot baseline
            - Owner SID on the restored file matches the snapshot baseline
        """


@pytest.mark.tier3
@pytest.mark.windows
class TestFileRestoreWindowsDriveRoot:
    """
    Tests for Windows file restore from drive root paths.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and filerestore user configured
        - Backup volume with a file at a Windows drive root path (e.g., E:\\file.txt)
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16771")
    def test_windows_vm_restore_from_drive_root_path(self):
        """
        Test that file restore on Windows VM succeeds when the source file is at a drive root.

        Preconditions:
            - Running Windows VM with guest helper installed
            - Backup volume containing a file at drive root E:\\file.txt with known content

        Steps:
            1. Create VMFileRestore with drive-root source path (E:\\file.txt) and target path (C:\\restored\\file.txt)
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check file presence at target path inside Windows VM using Test-Path
            4. Read file content and compare with source

        Expected:
            - File exists at C:\\restored\\file.txt with content equal to the source
        """
