"""
File-Level Restore Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/VIRTSTRAT-480_file_level_restore.md
Jira: https://redhat.atlassian.net/browse/VIRTSTRAT-480 # <skip-jira-utils-check>
"""

import pytest

from tests.storage.file_level_restore.constants import (
    LINUX_VENDOR_RESTORE_CR_NAME,
    WINDOWS_ACL_PVC_RESTORE_CR_NAME,
    WINDOWS_ACL_SNAPSHOT_RESTORE_CR_NAME,
    WINDOWS_DRIVE_ROOT_RESTORE_CR_NAME,
    WINDOWS_FILE_COUNT_RESTORE_CR_NAME,
    WINDOWS_MULTI_FILE_COUNT,
    WINDOWS_RESTORE_TEST_DIRECTORY,
)
from tests.storage.file_level_restore.utils import (
    VirtualMachineFileRestore,
    assert_file_restore_operator_pod_running,
    assert_successful_restore_cleanup,
    assert_windows_ntfs_acl_matches,
    count_files_in_windows_directory,
    get_restored_files_count,
    wait_for_file_restore_operator_ready,
    wait_for_file_restore_phase,
    windows_data_disk_path,
    windows_guest_path,
)
from utilities.storage import run_command_on_vm_and_check_output, verify_file_in_windows_vm


class TestFileRestoreOperatorDeployment:
    """
    Tests for vm-file-restore-operator deployment via HCO-managed lifecycle.

    Preconditions:
        - OpenShift Virtualization installed via HyperConverged CR (HCO-managed lifecycle)
        - openshift-cnv namespace exists
    """

    @pytest.mark.polarion("CNV-16810")
    def test_file_restore_operator_deployed_after_cnv_install(self, admin_client):
        """
        Test that vm-file-restore-operator is deployed and running after OpenShift Virtualization
        installation via HCO-managed lifecycle.

        Preconditions:
            - OpenShift Virtualization installed via HyperConverged CR (HCO-managed lifecycle)
            - openshift-cnv namespace exists

        Steps:
            1. Wait for vm-file-restore-operator deployment and SSH ConfigMap to become ready
            2. Verify vm-file-restore-operator pod is Running

        Expected:
            - vm-file-restore-operator deployment exists and its pod is Running
        """
        wait_for_file_restore_operator_ready(admin_client=admin_client)
        assert_file_restore_operator_pod_running(admin_client=admin_client)


@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreBackupVendorWorkflow:
    """
    End-to-end restore workflow tests simulating backup vendor integration.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
        - Backup PVC available as restore source
        - Target file content recorded before deletion (for comparison after restore)
    """

    @pytest.mark.polarion("CNV-16767")
    def test_restore_workflow_from_api(
        self,
        admin_client,
        namespace,
        file_restore_linux_vm,
        linux_backup_pvc,
        deleted_linux_test_file_on_data_disk,
    ):
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
        restore_path, expected_content = deleted_linux_test_file_on_data_disk
        with VirtualMachineFileRestore(
            name=LINUX_VENDOR_RESTORE_CR_NAME,
            namespace=namespace.name,
            target_vm_name=file_restore_linux_vm.name,
            source_pvc_name=linux_backup_pvc.name,
            source_path=restore_path,
            client=admin_client,
        ) as file_restore:
            wait_for_file_restore_phase(
                file_restore=file_restore,
                target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
            )
            restored_file_count = get_restored_files_count(file_restore=file_restore)
            assert restored_file_count == 1, f"VMFileRestore reported {restored_file_count} restored files, expected 1"
            run_command_on_vm_and_check_output(
                vm=file_restore_linux_vm,
                command=f"cat {restore_path}",
                expected_result=expected_content,
            )
            assert_successful_restore_cleanup(
                vm=file_restore_linux_vm,
                restore_cr_name=file_restore.name,
                namespace_name=namespace.name,
                admin_client=admin_client,
                snapshot_source=False,
            )


@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreWindowsGuestFileCount:
    """
    Tests for file count reporting accuracy on Windows VM guests.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
        - Backup volume (PVC or VolumeSnapshot) with a known number of files on NTFS filesystem
    """

    @pytest.mark.polarion("CNV-16770")
    @pytest.mark.usefixtures("deleted_windows_multi_files_on_data_disk")
    def test_file_count_matches_transferred_on_windows_vm(
        self,
        admin_client,
        namespace,
        windows_file_restore_vm,
        windows_multi_file_data_disk_snapshot,
    ):
        """
        Test that the restored file count in status matches actual files transferred on a Windows VM.

        Preconditions:
            - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
            - Backup volume (PVC or VolumeSnapshot) containing a known number of NTFS files
            - Target files deleted from the Windows VM data disk

        Steps:
            1. Create VMFileRestore for the backup directory containing a known number of files
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check the file count reported by the restore resource
            4. Count the restored files inside the Windows VM

        Expected:
            - File count in VMFileRestore status equals the actual number of files restored in the Windows VM
        """
        restore_directory = windows_guest_path(
            guest_path=windows_data_disk_path(relative_path=WINDOWS_RESTORE_TEST_DIRECTORY),
        )
        with VirtualMachineFileRestore(
            name=WINDOWS_FILE_COUNT_RESTORE_CR_NAME,
            namespace=namespace.name,
            target_vm_name=windows_file_restore_vm.name,
            source_snapshot_name=windows_multi_file_data_disk_snapshot.name,
            source_path=restore_directory,
            client=admin_client,
        ) as file_restore:
            wait_for_file_restore_phase(
                file_restore=file_restore,
                target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
            )
            reported_file_count = get_restored_files_count(file_restore=file_restore)
            actual_file_count = count_files_in_windows_directory(
                vm=windows_file_restore_vm,
                directory_path=restore_directory,
            )
            assert reported_file_count == WINDOWS_MULTI_FILE_COUNT, (
                f"VMFileRestore reported {reported_file_count} files, expected {WINDOWS_MULTI_FILE_COUNT}"
            )
            assert actual_file_count == WINDOWS_MULTI_FILE_COUNT, (
                f"Expected {WINDOWS_MULTI_FILE_COUNT} restored files in guest, found {actual_file_count}"
            )
            assert reported_file_count == actual_file_count, (
                f"Reported count {reported_file_count} does not match guest count {actual_file_count}"
            )
            assert_successful_restore_cleanup(
                vm=windows_file_restore_vm,
                restore_cr_name=file_restore.name,
                namespace_name=namespace.name,
                admin_client=admin_client,
                snapshot_source=True,
            )


@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreWindowsNTFSACLsAndOwnership:
    """
    Tests for NTFS ACLs and ownership preservation on Windows VM file restore.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
    """

    @pytest.mark.polarion("CNV-16768")
    def test_windows_vm_restore_from_backup_pvc_preserves_ntfs_acls_and_ownership(
        self,
        admin_client,
        namespace,
        windows_file_restore_vm,
        windows_backup_pvc,
        windows_ntfs_acl_baseline,
        deleted_windows_test_file_on_data_disk,
    ):
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
        guest_path, _ = deleted_windows_test_file_on_data_disk
        source_path = windows_guest_path(guest_path=guest_path)
        expected_acl, expected_owner = windows_ntfs_acl_baseline
        with VirtualMachineFileRestore(
            name=WINDOWS_ACL_PVC_RESTORE_CR_NAME,
            namespace=namespace.name,
            target_vm_name=windows_file_restore_vm.name,
            source_pvc_name=windows_backup_pvc.name,
            source_path=source_path,
            client=admin_client,
        ) as file_restore:
            wait_for_file_restore_phase(
                file_restore=file_restore,
                target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
            )
            assert_windows_ntfs_acl_matches(
                vm=windows_file_restore_vm,
                file_path=source_path,
                expected_acl=expected_acl,
                expected_owner=expected_owner,
            )
            assert_successful_restore_cleanup(
                vm=windows_file_restore_vm,
                restore_cr_name=file_restore.name,
                namespace_name=namespace.name,
                admin_client=admin_client,
                snapshot_source=False,
            )

    @pytest.mark.polarion("CNV-16769")
    def test_windows_vm_restore_from_snapshot_preserves_ntfs_acls_and_ownership(
        self,
        admin_client,
        namespace,
        windows_file_restore_vm,
        windows_data_disk_snapshot,
        windows_ntfs_acl_baseline,
        deleted_windows_test_file_for_snapshot,
    ):
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
        guest_path, _ = deleted_windows_test_file_for_snapshot
        source_path = windows_guest_path(guest_path=guest_path)
        expected_acl, expected_owner = windows_ntfs_acl_baseline
        with VirtualMachineFileRestore(
            name=WINDOWS_ACL_SNAPSHOT_RESTORE_CR_NAME,
            namespace=namespace.name,
            target_vm_name=windows_file_restore_vm.name,
            source_snapshot_name=windows_data_disk_snapshot.name,
            source_path=source_path,
            client=admin_client,
        ) as file_restore:
            wait_for_file_restore_phase(
                file_restore=file_restore,
                target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
            )
            assert_windows_ntfs_acl_matches(
                vm=windows_file_restore_vm,
                file_path=source_path,
                expected_acl=expected_acl,
                expected_owner=expected_owner,
            )
            assert_successful_restore_cleanup(
                vm=windows_file_restore_vm,
                restore_cr_name=file_restore.name,
                namespace_name=namespace.name,
                admin_client=admin_client,
                snapshot_source=True,
            )


@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreWindowsDriveRoot:
    """
    Tests for Windows file restore from drive root paths.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - Running Windows VM with OpenSSH Server and guest helper installed, and filerestore user SSH-configured
        - Backup volume with a file at a Windows drive root path
    """

    @pytest.mark.polarion("CNV-16771")
    def test_windows_vm_restore_from_drive_root_path(
        self,
        admin_client,
        namespace,
        windows_file_restore_vm,
        windows_drive_root_data_disk_snapshot,
        deleted_windows_drive_root_file,
    ):
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
        guest_path, expected_content = deleted_windows_drive_root_file
        source_path = windows_guest_path(guest_path=guest_path)
        with VirtualMachineFileRestore(
            name=WINDOWS_DRIVE_ROOT_RESTORE_CR_NAME,
            namespace=namespace.name,
            target_vm_name=windows_file_restore_vm.name,
            source_snapshot_name=windows_drive_root_data_disk_snapshot.name,
            source_path=source_path,
            client=admin_client,
        ) as file_restore:
            wait_for_file_restore_phase(
                file_restore=file_restore,
                target_phase=VirtualMachineFileRestore.Phase.SUCCEEDED,
            )
            verify_file_in_windows_vm(
                windows_vm=windows_file_restore_vm,
                file_name_with_path=guest_path,
                file_content=expected_content,
            )
            assert_successful_restore_cleanup(
                vm=windows_file_restore_vm,
                restore_cr_name=file_restore.name,
                namespace_name=namespace.name,
                admin_client=admin_client,
                snapshot_source=True,
            )


@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreRootDiskToOriginalPath:
    """
    Tests for restoring files from root disk backup to their original location on a running Linux VM.

    Root-disk snapshots use online VirtualMachineSnapshot on a root-only RHEL VM (no secondary
    data disk). KubeVirt uses QEMU guest-agent fsfreeze to quiesce mounted filesystems before snapshot.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running root-only Linux VM with guest helper installed and filerestore user SSH-configured
    """

    @pytest.mark.polarion("CNV-16811")
    def test_restore_from_root_disk_snapshot_to_original_path(
        self,
        admin_client,
        namespace,
        file_restore_linux_root_only_vm,
        deleted_linux_test_file_on_root_disk,
        linux_root_disk_snapshot_file_restore,
    ):
        """
        Test that files are restored from a root disk VolumeSnapshot to their original location
        in a running Linux VM.

        Preconditions:
            - Running root-only Linux VM with guest helper installed and filerestore user SSH-configured
            - Root-disk VolumeSnapshot from an online VirtualMachineSnapshot marked readyToUse=true
            - Target file original content recorded and the file deleted from the VM root disk

        Steps:
            1. Create VMFileRestore from root disk VolumeSnapshot targeting the original file path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Compare restored file content against the recorded original
            4. Check the namespace for temporary resources left over from the restore operation

        Expected:
            - Restored file content matches the recorded original
            - File is restored to its original path on the running Linux VM
            - Temporary resources from the operation are cleaned up
        """
        restore_path, expected_content = deleted_linux_test_file_on_root_disk
        run_command_on_vm_and_check_output(
            vm=file_restore_linux_root_only_vm,
            command=f"cat {restore_path}",
            expected_result=expected_content,
        )
        assert_successful_restore_cleanup(
            vm=file_restore_linux_root_only_vm,
            restore_cr_name=linux_root_disk_snapshot_file_restore.name,
            namespace_name=namespace.name,
            admin_client=admin_client,
            snapshot_source=True,
        )

    @pytest.mark.polarion("CNV-16812")
    def test_restore_from_root_disk_backup_pvc_to_original_path(
        self,
        admin_client,
        namespace,
        file_restore_linux_root_only_vm,
        deleted_linux_test_file_on_root_disk_from_backup,
        linux_root_disk_backup_pvc_file_restore,
    ):
        """
        Test that files are restored from a root disk backup PVC to their original location
        in a running Linux VM.

        Preconditions:
            - Running root-only Linux VM with guest helper installed and filerestore user SSH-configured
            - Backup PVC cloned from the root-disk VolumeSnapshot created by VirtualMachineSnapshot
            - Target file original content recorded and the file deleted from the VM root disk

        Steps:
            1. Create VMFileRestore from root disk backup PVC targeting the original file path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Compare restored file content against the recorded original
            4. Check the namespace for temporary resources left over from the restore operation

        Expected:
            - Restored file content matches the recorded original
            - File is restored to its original path on the running Linux VM
            - Temporary resources from the operation are cleaned up
        """
        restore_path, expected_content = deleted_linux_test_file_on_root_disk_from_backup
        run_command_on_vm_and_check_output(
            vm=file_restore_linux_root_only_vm,
            command=f"cat {restore_path}",
            expected_result=expected_content,
        )
        assert_successful_restore_cleanup(
            vm=file_restore_linux_root_only_vm,
            restore_cr_name=linux_root_disk_backup_pvc_file_restore.name,
            namespace_name=namespace.name,
            admin_client=admin_client,
            snapshot_source=False,
        )


@pytest.mark.incremental
@pytest.mark.usefixtures("file_restore_operator")
class TestFileRestoreSequentialFromSameSnapshot:
    """
    Tests for data disk VolumeSnapshot restore and sequential restore from the same snapshot.

    Preconditions:
        - vm-file-restore-operator deployed and running in openshift-cnv namespace
        - VolumeSnapshot-capable StorageClass available
        - Running Linux VM with guest helper installed and filerestore user SSH-configured
        - VM data disk with two distinct test files
        - VolumeSnapshot of the VM data disk with both test files available
    """

    @pytest.mark.polarion("CNV-16813")
    def test_restore_from_data_disk_snapshot(
        self,
        admin_client,
        namespace,
        file_restore_linux_vm,
        deleted_first_linux_file_on_data_disk,
        first_linux_data_disk_snapshot_file_restore,
    ):
        """
        Test that files are restored from a data disk VolumeSnapshot in a running Linux VM
        and temporary resources are cleaned up after the operation.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - VolumeSnapshot of the VM data disk with two distinct test files available
            - First target file deleted from the VM data disk after snapshot
            - Original content recorded for the first target file before deletion

        Steps:
            1. Create VMFileRestore from the data disk VolumeSnapshot targeting the deleted file path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Check the namespace for temporary resources left over from the restore operation
            4. Compare restored file content against the recorded original

        Expected:
            - Restore operation from the data disk VolumeSnapshot reaches Succeeded phase
            - Restored file content matches the recorded original
            - Temporary resources from the operation are cleaned up
        """
        restore_path, expected_content = deleted_first_linux_file_on_data_disk
        run_command_on_vm_and_check_output(
            vm=file_restore_linux_vm,
            command=f"cat {restore_path}",
            expected_result=expected_content,
        )
        assert_successful_restore_cleanup(
            vm=file_restore_linux_vm,
            restore_cr_name=first_linux_data_disk_snapshot_file_restore.name,
            namespace_name=namespace.name,
            admin_client=admin_client,
            snapshot_source=True,
        )

    @pytest.mark.polarion("CNV-16815")
    def test_second_restore_from_same_data_disk_snapshot(
        self,
        admin_client,
        namespace,
        file_restore_linux_vm,
        linux_two_test_files_on_data_disk,
        deleted_second_linux_file_on_data_disk,
        second_linux_data_disk_snapshot_file_restore,
    ):
        """
        Test that a second restore from the same data disk VolumeSnapshot completes successfully.

        Preconditions:
            - Running Linux VM with guest helper installed and filerestore user SSH-configured
            - VolumeSnapshot of the VM data disk with two distinct test files available
            - Restore from the data disk VolumeSnapshot completed successfully
            - Second target file deleted from the VM data disk after snapshot
            - Original content recorded for the second target file before deletion

        Steps:
            1. Create a second VMFileRestore from the same data disk VolumeSnapshot targeting the deleted file path
            2. Wait for VMFileRestore to reach Succeeded phase
            3. Compare restored file content against the recorded original
            4. Check the namespace for temporary resources left over from the restore operation

        Expected:
            - Second restore operation from the same data disk VolumeSnapshot reaches Succeeded phase
            - Restored file content matches the recorded original
            - Temporary resources from the operation are cleaned up
            - The first restored file remains present and correct after the second restore
        """
        restore_path, expected_content = deleted_second_linux_file_on_data_disk
        first_restore_path, first_expected_content = linux_two_test_files_on_data_disk[0]
        run_command_on_vm_and_check_output(
            vm=file_restore_linux_vm,
            command=f"cat {restore_path}",
            expected_result=expected_content,
        )
        run_command_on_vm_and_check_output(
            vm=file_restore_linux_vm,
            command=f"cat {first_restore_path}",
            expected_result=first_expected_content,
        )
        assert_successful_restore_cleanup(
            vm=file_restore_linux_vm,
            restore_cr_name=second_linux_data_disk_snapshot_file_restore.name,
            namespace_name=namespace.name,
            admin_client=admin_client,
            snapshot_source=True,
        )
