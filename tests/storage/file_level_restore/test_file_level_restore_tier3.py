"""
File-Level Restore Windows Guest Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest


class TestFileRestoreWindowsGuestFileCount:
    """
    Tests for file count reporting accuracy on Windows VM guests.

    Markers:
        - tier3
        - windows

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
        - Backup volume with a known number of files on NTFS filesystem
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16770")
    def test_file_count_matches_transferred_on_windows_vm(self):
        """
        Test that the restored file count in status matches actual files transferred on a Windows VM.

        Priority: P0

        Preconditions:
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - Backup volume containing a known number of NTFS files
            - Target files deleted from the Windows VM data disk

        Steps:
            1. Create VMFileRestore for the backup volume with a known number of files
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check the file count reported by the restore resource
            4. Count the restored files inside the Windows VM

        Expected:
            - File count in VMFileRestore status equals the actual number of files restored in the Windows VM
        """


class TestFileRestoreWindowsNTFSMetadata:
    """
    Tests for NTFS metadata preservation on Windows VM file restore.

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
    def test_windows_vm_restore_from_backup_pvc_preserves_ntfs_metadata(self):
        """
        Test that file restore on Windows VM from a backup PVC preserves NTFS metadata and ACLs.

        Priority: P0

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
    def test_windows_vm_restore_from_snapshot_preserves_ntfs_metadata(self):
        """
        Test that file restore on Windows VM from a volume snapshot preserves NTFS metadata and ACLs.

        Priority: P0

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

        Priority: P0

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
