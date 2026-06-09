"""
CBT (Changed Block Tracking) backup and restore validation

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

Preconditions:
    - incrementalBackup feature gate enabled
    - CBT label selectors configured
    - Test namespace opted in to CBT
"""

import pytest

from tests.storage.cbt.utils import (
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_INCREMENTAL_TEST_DATA,
    CBT_INCREMENTAL_TEST_DATA_FILE,
    CBT_TEST_DATA,
    read_file_content_from_vm,
)


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-full"}],
    indirect=True,
)
class TestFullBackupRestore:
    """
    Full backup and restore validation for push and pull modes.

    Preconditions:
        - Running VM with CBT enabled
        - Test data written to VM
    """

    @pytest.mark.polarion("CNV-15997")
    def test_full_backup_push_mode_restore(
        self,
        test_data_from_restored_vm_push_mode,
    ):
        """
        Test that a VM can be backed up (push mode) and restored from a full backup.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the full backup
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data is present
        """
        assert test_data_from_restored_vm_push_mode == CBT_TEST_DATA

    @pytest.mark.polarion("CNV-15996")
    def test_full_backup_pull_mode_restore(
        self,
        test_data_from_restored_vm_pull_mode,
    ):
        """
        Test that a full backup in pull mode can be performed and the VM can be restored.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the backup
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data is present
        """
        assert test_data_from_restored_vm_pull_mode == CBT_TEST_DATA


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-incr"}],
    indirect=True,
)
class TestIncrementalBackupRestore:
    """
    Incremental backup and restore validation for push and pull modes.

    Preconditions:
        - Running VM with CBT enabled
        - Full backup completed
        - Test data written to VM
    """

    @pytest.mark.polarion("CNV-15998")
    def test_incremental_backup_push_mode_restore(
        self,
        restored_vm_from_incremental_backup_push_mode,
    ):
        """
        Test that a VM can be backed up (push mode) and restored from an incremental backup.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Write new test data to VM
            2. Perform an incremental backup in push mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the incremental backup
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and all test data is present
        """
        assert (
            read_file_content_from_vm(
                vm=restored_vm_from_incremental_backup_push_mode,
                file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
            )
            == CBT_TEST_DATA
        )
        assert (
            read_file_content_from_vm(
                vm=restored_vm_from_incremental_backup_push_mode,
                file_path=CBT_INCREMENTAL_TEST_DATA_FILE,
            )
            == CBT_INCREMENTAL_TEST_DATA
        )

    @pytest.mark.polarion("CNV-16000")
    def test_incremental_backup_pull_mode_restore(
        self,
        restored_vm_from_incremental_backup_pull_mode,
    ):
        """
        Test that an incremental backup in pull mode can be performed and the VM can be restored.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Write new test data to VM
            2. Perform an incremental backup in pull mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the incremental backup
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and all test data is present
        """
        assert (
            read_file_content_from_vm(
                vm=restored_vm_from_incremental_backup_pull_mode,
                file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
            )
            == CBT_TEST_DATA
        )
        assert (
            read_file_content_from_vm(
                vm=restored_vm_from_incremental_backup_pull_mode,
                file_path=CBT_INCREMENTAL_TEST_DATA_FILE,
            )
            == CBT_INCREMENTAL_TEST_DATA
        )


class TestMultipleIncrementalBackups:
    """
    Multiple incremental backups and restore validation.

    Preconditions:
        - Running VM with CBT enabled
        - Full backup completed
        - Test data written to VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16002")
    def test_multiple_incremental_backups_push_mode_restore(self):
        """
        Test that a VM can be restored from multiple incremental backups (push mode) with all data present.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Write additional test data to VM
            2. Perform first incremental backup in push mode
            3. Write more test data to VM
            4. Perform second incremental backup in push mode
            5. Wait for all backups to complete
            6. Delete the original VM
            7. Restore VM from the latest incremental backup
            8. Start the restored VM

        Expected:
            - Restored VM boots successfully and all test data is present
        """

    @pytest.mark.polarion("CNV-16001")
    def test_multiple_incremental_backups_pull_mode_restore(self):
        """
        Test that a VM can be restored from multiple incremental backups (pull mode) with all data present.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Write additional test data to VM
            2. Perform first incremental backup in pull mode
            3. Write more test data to VM
            4. Perform second incremental backup in pull mode
            5. Wait for all backups to complete
            6. Delete the original VM
            7. Restore VM from the latest incremental backup
            8. Start the restored VM

        Expected:
            - Restored VM boots successfully and all test data is present
        """


class TestMultipleDiskBackup:
    """
    Backup and restore validation for VMs with multiple disks.

    Preconditions:
        - Running VM with CBT enabled
        - VM has boot disk and data disk
        - Test data written to both disks
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16003")
    def test_backup_multiple_disks_push_mode_restore(self):
        """
        Test that a VM with multiple disks can be backed up (push mode) and restored with all disks accessible.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the backup with both disks
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data from both disks is present
        """

    @pytest.mark.polarion("CNV-16004")
    def test_backup_multiple_disks_pull_mode_restore(self):
        """
        Test that a VM with multiple disks can be backed up (pull mode) and restored with all disks accessible.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for backup to complete
            4. Delete the original VM
            5. Restore VM from the backup with both disks
            6. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data from both disks is present
        """


@pytest.mark.rwx_default_storage
class TestBackupAfterLiveMigration:
    """
    Backup and restore after VM live migration (requires RWX shared storage).

    Preconditions:
        - Running VM with CBT enabled
        - VM disks on RWX backend PVC
        - At least two worker nodes available
        - Test data written to VM
        - Full backup completed before migration
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16005")
    def test_incremental_backup_after_live_migration_push_mode(self):
        """
        Test that a VM can be backed up (push mode) after live migration and restored with post-migration data.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Live migrate the VM to another node
            2. Wait for migration to complete
            3. Write new test data to VM
            4. Perform an incremental backup in push mode
            5. Wait for backup to complete
            6. Delete the original VM
            7. Restore VM from the incremental backup
            8. Start the restored VM

        Expected:
            - Restored VM boots successfully and pre-migration and post-migration test data are present
        """

    @pytest.mark.polarion("CNV-16006")
    def test_incremental_backup_after_live_migration_pull_mode(self):
        """
        Test that a VM can be backed up (pull mode) after live migration and restored with post-migration data.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Live migrate the VM to another node
            2. Wait for migration to complete
            3. Write new test data to VM
            4. Perform an incremental backup in pull mode
            5. Wait for backup to complete
            6. Delete the original VM
            7. Restore VM from the incremental backup
            8. Start the restored VM

        Expected:
            - Restored VM boots successfully and pre-migration and post-migration test data are present
        """


@pytest.mark.usefixtures("declarative_hotplug_volumes_feature_gate_enabled")
class TestHotplugBackup:
    """
    Backup and restore validation for VMs with hotplugged disks.

    Preconditions:
        - Running VM with CBT enabled
        - Full backup completed
        - Test data written to VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16009")
    def test_backup_with_hotplugged_disk_push_mode_restore(self):
        """
        Test that a VM with hotplugged disk can be backed up (push mode) and restored with hotplugged disk data accessible.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Hotplug a new DataVolume to the running VM
            2. Mount the hotplugged disk in the VM
            3. Write test data to hotplugged disk
            4. Perform a full backup in push mode
            5. Wait for backup to complete
            6. Delete the original VM
            7. Delete the hotplugged DataVolume
            8. Restore VM from the backup with both disks
            9. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data from both original and hotplugged disks is present
        """

    @pytest.mark.polarion("CNV-16010")
    def test_backup_with_hotplugged_disk_pull_mode_restore(self):
        """
        Test that a VM with hotplugged disk can be backed up (pull mode) and restored with hotplugged disk data accessible.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Hotplug a new DataVolume to the running VM
            2. Mount the hotplugged disk in the VM
            3. Write test data to hotplugged disk
            4. Perform a full backup in pull mode
            5. Wait for backup to complete
            6. Delete the original VM
            7. Delete the hotplugged DataVolume
            8. Restore VM from the backup with both disks
            9. Start the restored VM

        Expected:
            - Restored VM boots successfully and test data from both original and hotplugged disks is present
        """


class TestBackupErrorHandling:
    """
    Backup error handling and negative scenarios.

    Preconditions:
        - Running VM with CBT enabled
        - Test data written to VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16023")
    def test_backup_fails_when_storage_full_push_mode(self):
        """
        [NEGATIVE] Test that backup fails gracefully when backup PVC is full.

        Preconditions:
            - Backup PVC with insufficient capacity for the VM's data
            - VM with data exceeding backup PVC capacity

        Steps:
            1. Create a backup tracker for the VM
            2. Attempt full backup in push mode to the small PVC
            3. Wait for backup operation to complete

        Expected:
            - Backup fails with storage full error, leaves no partial backup data on the target PVC, and the VM remains accessible and unaffected
        """

    @pytest.mark.polarion("CNV-16024")
    def test_backup_fails_when_storage_full_pull_mode(self):
        """
        [NEGATIVE] Test that backup fails gracefully when scratch PVC is full in pull mode.

        Preconditions:
            - Scratch PVC with insufficient capacity for the VM's data
            - VM with data exceeding scratch PVC capacity

        Steps:
            1. Create a backup tracker for the VM
            2. Attempt full backup in pull mode to the small scratch PVC
            3. Wait for backup operation to complete

        Expected:
            - Backup fails with storage full error, leaves no partial backup data on the scratch PVC, and the VM remains accessible and unaffected
        """


class TestConcurrentBackups:
    """
    Concurrent backup operations on multiple VMs.

    Preconditions:
        - 5 running VMs with CBT enabled
        - Test data written to each VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16011")
    def test_concurrent_backups_push_mode_restore(self):
        """
        Test that concurrent backups (push mode) on multiple VMs complete successfully and all VMs can be restored.

        Preconditions:
            - Backup PVCs available for each VM

        Steps:
            1. Create backup trackers for all VMs
            2. Start simultaneous backups in push mode on all VMs
            3. Wait for all backups to complete
            4. Delete all original VMs
            5. Restore all VMs from their respective backups
            6. Start all restored VMs

        Expected:
            - All restored VMs boot successfully and test data is present in each VM
        """

    @pytest.mark.polarion("CNV-16012")
    def test_concurrent_backups_pull_mode_restore(self):
        """
        Test that concurrent backups (pull mode) on multiple VMs complete successfully and all VMs can be restored.

        Preconditions:
            - Scratch PVCs available for each VM (pull mode)

        Steps:
            1. Create backup trackers for all VMs
            2. Start simultaneous backups in pull mode on all VMs
            3. Wait for all backups to complete
            4. Delete all original VMs
            5. Restore all VMs from their respective backups
            6. Start all restored VMs

        Expected:
            - All restored VMs boot successfully and test data is present in each VM
        """


@pytest.mark.tier3
class TestWindowsVMFullBackup:
    """
    Full backup and restore validation for Windows VMs.

    Preconditions:
        - Running Windows VM with CBT enabled
        - Test data written to Windows VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16013")
    def test_windows_vm_full_backup_push_mode_restore(self):
        """
        Test that a Windows VM can be backed up (push mode) and restored from a full backup.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the Windows VM
            2. Perform a full backup in push mode
            3. Wait for backup to complete
            4. Delete the original Windows VM
            5. Restore Windows VM from the backup
            6. Start the restored VM

        Expected:
            - Restored Windows VM boots successfully and test data is present
        """

    @pytest.mark.polarion("CNV-16014")
    def test_windows_vm_full_backup_pull_mode_restore(self):
        """
        Test that a Windows VM can be backed up (pull mode) and restored from a full backup.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the Windows VM
            2. Perform a full backup in pull mode
            3. Wait for backup to complete
            4. Delete the original Windows VM
            5. Restore Windows VM from the backup
            6. Start the restored VM

        Expected:
            - Restored Windows VM boots successfully and test data is present
        """


@pytest.mark.tier3
class TestWindowsVMIncrementalBackup:
    """
    Incremental backup and restore validation for Windows VMs.

    Preconditions:
        - Running Windows VM with CBT enabled
        - Full backup completed
        - Test data written to Windows VM
    """

    __test__ = False  # Exclude from PR1 - reserved for future PR

    @pytest.mark.polarion("CNV-16015")
    def test_windows_vm_incremental_backup_push_mode_restore(self):
        """
        Test that a Windows VM can be backed up (push mode) and restored from an incremental backup.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Write new test data to Windows VM
            2. Perform an incremental backup in push mode
            3. Wait for backup to complete
            4. Delete the original Windows VM
            5. Restore Windows VM from the incremental backup
            6. Start the restored VM

        Expected:
            - Restored Windows VM boots successfully and all test data is present
        """

    @pytest.mark.polarion("CNV-16016")
    def test_windows_vm_incremental_backup_pull_mode_restore(self):
        """
        Test that a Windows VM can be backed up (pull mode) and restored from an incremental backup.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Write new test data to Windows VM
            2. Perform an incremental backup in pull mode
            3. Wait for backup to complete
            4. Delete the original Windows VM
            5. Restore Windows VM from the incremental backup
            6. Start the restored VM

        Expected:
            - Restored Windows VM boots successfully and all test data is present
        """
