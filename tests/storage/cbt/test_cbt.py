"""
CBT (Changed Block Tracking) backup validation (backup success only)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

Preconditions:
    - incrementalBackup feature gate enabled
    - CBT label selectors configured
    - Test namespace opted in to CBT
"""

import pytest

from tests.storage.cbt.constants import (
    CBT_BACKUP_CHAIN_INCREMENTAL_COUNT,
    CBT_BACKUP_TYPE_FULL,
    CBT_BACKUP_TYPE_INCREMENTAL,
    CBT_MULTI_DISK_DATA_DISK_COUNT,
)
from tests.storage.cbt.utils import (
    assert_backup_status_includes_volumes,
    attached_data_disk_names,
)
from utilities.constants.virt import DV_DISK


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-full"}],
    indirect=True,
)
class TestFullBackup:
    """
    Full backup validation for push and pull modes (backup success only).

    Preconditions:
        - Running VM with CBT enabled
        - Test data written to VM
    """

    @pytest.mark.polarion("CNV-15997")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_full_backup_push_mode(
        self,
        completed_push_backup_chain,
    ):
        """
        Test that a full backup in push mode completes successfully.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for the backup to complete

        Expected:
            - Full backup completes and includes the boot disk
        """
        full_backup = completed_push_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=full_backup.name,
            backup_status=full_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )

    @pytest.mark.polarion("CNV-15996")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_full_backup_pull_mode(
        self,
        ready_pull_backup_chain,
    ):
        """
        Test that a full backup in pull mode becomes ready for export.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for the backup export to become ready

        Expected:
            - Backup export is ready and includes the boot disk
        """
        backup_name, backup_status = ready_pull_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-incr"}],
    indirect=True,
)
class TestIncrementalBackup:
    """
    Incremental backup validation for push and pull modes (backup success only).

    Preconditions:
        - Running VM with CBT enabled
        - Full backup completed
        - Test data written to VM
    """

    @pytest.mark.polarion("CNV-15998")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": 1}],
        indirect=True,
    )
    def test_incremental_backup_push_mode(
        self,
        completed_push_backup_chain,
    ):
        """
        Test that an incremental backup in push mode completes successfully.

        Preconditions:
            - Backup PVC available
            - Full backup completed in push mode

        Steps:
            1. Write new test data to VM
            2. Perform an incremental backup in push mode
            3. Wait for the backup to complete

        Expected:
            - Incremental backup completes and includes the boot disk
        """
        incremental_backup = completed_push_backup_chain[-1]
        assert_backup_status_includes_volumes(
            backup_name=incremental_backup.name,
            backup_status=incremental_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )

    @pytest.mark.polarion("CNV-16000")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 1}],
        indirect=True,
    )
    def test_incremental_backup_pull_mode(
        self,
        ready_pull_backup_chain,
    ):
        """
        Test that an incremental backup in pull mode becomes ready for export.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Perform a full backup in pull mode and wait until export is ready
            2. Delete the full pull-mode backup
            3. Write new test data to VM
            4. Perform an incremental backup in pull mode
            5. Wait for the backup export to become ready

        Expected:
            - Incremental backup export is ready and includes the boot disk
        """
        backup_name, backup_status = ready_pull_backup_chain[-1]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-multi-incr"}],
    indirect=True,
)
class TestMultipleIncrementalBackups:
    """
    Multiple sequential incremental backups validation (backup success only).

    Preconditions:
        - Running VM with CBT enabled
        - Test data written to VM
    """

    @pytest.mark.polarion("CNV-16002")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": CBT_BACKUP_CHAIN_INCREMENTAL_COUNT}],
        indirect=True,
    )
    def test_multiple_incremental_backups_push_mode(
        self,
        completed_push_backup_chain,
    ):
        """
        Test that a full backup followed by multiple sequential incremental backups all complete
        successfully in push mode.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Perform a full backup in push mode and wait until it completes
            2. Write new test data to VM, perform an incremental backup in push mode, and wait
               until it completes
            3. Repeat step 2 two more times

        Expected:
            - Every backup in the chain completes and includes the boot disk, with the first
              backup typed Full and every following backup typed Incremental
        """
        expected_chain_length = 1 + CBT_BACKUP_CHAIN_INCREMENTAL_COUNT
        assert len(completed_push_backup_chain) == expected_chain_length, (
            f"Expected 1 full + {CBT_BACKUP_CHAIN_INCREMENTAL_COUNT} incremental backups, "
            f"got {len(completed_push_backup_chain)}"
        )
        for backup_index, backup in enumerate(completed_push_backup_chain):
            expected_backup_type = CBT_BACKUP_TYPE_FULL if backup_index == 0 else CBT_BACKUP_TYPE_INCREMENTAL
            assert_backup_status_includes_volumes(
                backup_name=backup.name,
                backup_status=backup.instance.to_dict()["status"],
                expected_volume_names=[DV_DISK],
                expected_backup_type=expected_backup_type,
            )

    @pytest.mark.polarion("CNV-16001")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": CBT_BACKUP_CHAIN_INCREMENTAL_COUNT}],
        indirect=True,
    )
    def test_multiple_incremental_backups_pull_mode(
        self,
        ready_pull_backup_chain,
    ):
        """
        Test that a full backup followed by multiple sequential incremental backups all become
        ready for export in pull mode.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Perform a full backup in pull mode and wait until export is ready
            2. Delete the previous backup, write new test data to VM, perform an incremental
               backup in pull mode, and wait until export is ready
            3. Repeat step 2 two more times

        Expected:
            - Every backup in the chain is ready for export and includes the boot disk, with the
              first backup typed Full and every following backup typed Incremental
        """
        expected_chain_length = 1 + CBT_BACKUP_CHAIN_INCREMENTAL_COUNT
        assert len(ready_pull_backup_chain) == expected_chain_length, (
            f"Expected 1 full + {CBT_BACKUP_CHAIN_INCREMENTAL_COUNT} incremental backups, "
            f"got {len(ready_pull_backup_chain)}"
        )
        for backup_index, (backup_name, backup_status) in enumerate(ready_pull_backup_chain):
            expected_backup_type = CBT_BACKUP_TYPE_FULL if backup_index == 0 else CBT_BACKUP_TYPE_INCREMENTAL
            assert_backup_status_includes_volumes(
                backup_name=backup_name,
                backup_status=backup_status,
                expected_volume_names=[DV_DISK],
                expected_backup_type=expected_backup_type,
            )


@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-multi-disk", "data_disk_count": CBT_MULTI_DISK_DATA_DISK_COUNT}],
    indirect=True,
)
class TestMultipleDiskBackup:
    """
    Full backup validation for VMs with multiple disks (backup success only).

    Preconditions:
        - Running VM with CBT enabled
        - VM has a boot disk and two data disks
        - Test data written to all disks
    """

    @pytest.mark.polarion("CNV-16003")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_backup_multiple_disks_push_mode(
        self,
        completed_push_backup_chain,
        vm_with_cbt_label,
    ):
        """
        Test that a full backup in push mode completes successfully for a VM with multiple disks.

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for the backup to complete

        Expected:
            - Full backup completes and includes the boot disk and all data disks
        """
        data_disk_names = attached_data_disk_names(vm=vm_with_cbt_label)
        assert len(data_disk_names) == CBT_MULTI_DISK_DATA_DISK_COUNT, (
            f"VM {vm_with_cbt_label.name} has data disks {data_disk_names}, expected {CBT_MULTI_DISK_DATA_DISK_COUNT}"
        )
        full_backup = completed_push_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=full_backup.name,
            backup_status=full_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK, *data_disk_names],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )

    @pytest.mark.polarion("CNV-16004")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_backup_multiple_disks_pull_mode(
        self,
        ready_pull_backup_chain,
        vm_with_cbt_label,
    ):
        """
        Test that a full backup in pull mode becomes ready for export for a VM with multiple disks.

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for the backup export to become ready

        Expected:
            - Backup export is ready and includes the boot disk and all data disks
        """
        data_disk_names = attached_data_disk_names(vm=vm_with_cbt_label)
        assert len(data_disk_names) == CBT_MULTI_DISK_DATA_DISK_COUNT, (
            f"VM {vm_with_cbt_label.name} has data disks {data_disk_names}, expected {CBT_MULTI_DISK_DATA_DISK_COUNT}"
        )
        backup_name, backup_status = ready_pull_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK, *data_disk_names],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )


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

    __test__ = False  # STD placeholder - not yet implemented

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


class TestHotplugBackup:
    """
    Backup and restore validation for VMs with hotplugged disks.

    Preconditions:
        - Running VM with CBT enabled
        - Full backup completed
        - Test data written to VM
    """

    __test__ = False  # STD placeholder - not yet implemented

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

    __test__ = False  # STD placeholder - not yet implemented

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

    __test__ = False  # STD placeholder - not yet implemented

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
@pytest.mark.windows
class TestWindowsVMFullBackup:
    """
    Full backup and restore validation for Windows VMs.

    Preconditions:
        - Running Windows VM with CBT enabled
        - Test data written to Windows VM
    """

    __test__ = False  # STD placeholder - not yet implemented

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
@pytest.mark.windows
class TestWindowsVMIncrementalBackup:
    """
    Incremental backup and restore validation for Windows VMs.

    Preconditions:
        - Running Windows VM with CBT enabled
        - Full backup completed
        - Test data written to Windows VM
    """

    __test__ = False  # STD placeholder - not yet implemented

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
