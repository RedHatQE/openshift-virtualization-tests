"""
CBT (Changed Block Tracking) backup and integrity restore validation.

Restore is not a product API. Tests rebuild disks from the backup and check guest
data to prove the backup is usable.

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
    CBT_CONCURRENT_VM_COUNT,
    CBT_MULTI_DISK_DATA_DISK_COUNT,
)
from tests.storage.cbt.restore import assert_restored_cbt_vm_data
from tests.storage.cbt.utils import (
    assert_backup_status_includes_volumes,
    cbt_data_disk_volume_names,
    concurrent_backup_type,
)
from utilities.constants.virt import DV_DISK


# Required at collection for storage_class_matrix__module__.
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-full"}],
    indirect=True,
)
class TestFullBackup:
    """
    Full backup and integrity restore for push and pull modes.

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
        restored_vm_from_push_chain,
    ):
        """
        Test that a full backup in push mode completes and the VM can be restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for the backup to complete
            4. Delete the original VM
            5. Restore the VM disk from the backup
            6. Start the restored VM

        Expected:
            - Full backup completes and includes the boot disk, and the restored VM boots
              with the original test data
        """
        full_backup = completed_push_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=full_backup.name,
            backup_status=full_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_push_chain)

    @pytest.mark.polarion("CNV-15996")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_full_backup_pull_mode(
        self,
        ready_pull_backup_chain,
        restored_vm_from_pull_chain,
    ):
        """
        Test that a full backup in pull mode can be exported and the VM restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for the backup export to become ready
            4. Download the backup from the export
            5. Delete the original VM
            6. Restore the VM disk from the downloaded backup
            7. Start the restored VM

        Expected:
            - Backup export is ready and includes the boot disk, and the restored VM boots
              with the original test data
        """
        backup_name, backup_status = ready_pull_backup_chain.backups[0]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_pull_chain)


# Required at collection for storage_class_matrix__module__.
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-incr"}],
    indirect=True,
)
class TestIncrementalBackup:
    """
    Incremental backup and integrity restore for push and pull modes.

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
        restored_vm_from_push_chain,
    ):
        """
        Test that an incremental backup in push mode completes and the VM can be restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Backup PVC available
            - Full backup completed in push mode

        Steps:
            1. Write new test data to VM
            2. Perform an incremental backup in push mode
            3. Wait for the backup to complete
            4. Delete the original VM
            5. Restore the VM disk from the full and incremental backups
            6. Start the restored VM

        Expected:
            - Incremental backup completes and includes the boot disk, and the restored VM
              boots with the original test data and the data written before the incremental backup
        """
        incremental_backup = completed_push_backup_chain[-1]
        assert_backup_status_includes_volumes(
            backup_name=incremental_backup.name,
            backup_status=incremental_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_push_chain, incremental_indexes=[1])

    @pytest.mark.polarion("CNV-16000")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 1}],
        indirect=True,
    )
    def test_incremental_backup_pull_mode(
        self,
        ready_pull_backup_chain,
        restored_vm_from_pull_chain,
    ):
        """
        Test that an incremental backup in pull mode can be exported and the VM restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Perform a full backup in pull mode, wait until export is ready, and download it
            2. Delete the full pull-mode backup
            3. Write new test data to VM
            4. Perform an incremental backup in pull mode
            5. Wait for the backup export to become ready and download it
            6. Delete the original VM
            7. Restore the VM disk from the downloaded backups
            8. Start the restored VM

        Expected:
            - Incremental backup export is ready and includes the boot disk, and the restored
              VM boots with the original test data and the data written before the incremental backup
        """
        backup_name, backup_status = ready_pull_backup_chain.backups[-1]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_pull_chain, incremental_indexes=[1])


# Required at collection for storage_class_matrix__module__.
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-multi-incr"}],
    indirect=True,
)
class TestMultipleIncrementalBackups:
    """
    Multiple sequential incremental backups and integrity restore.

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
        restored_vm_from_push_chain,
    ):
        """
        Test that a full backup followed by multiple sequential incremental backups can restore
        the VM in push mode.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Backup PVC available

        Steps:
            1. Perform a full backup in push mode and wait until it completes
            2. Write new test data to VM, perform an incremental backup in push mode, and wait
               until it completes
            3. Repeat step 2 two more times
            4. Delete the original VM
            5. Restore the VM disk from the full backup and every incremental backup
            6. Start the restored VM

        Expected:
            - Every backup in the chain completes and includes the boot disk, with the first
              backup typed Full and every following backup typed Incremental, and the restored
              VM boots with the original test data and the data from every incremental backup
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
        assert_restored_cbt_vm_data(
            vm=restored_vm_from_push_chain,
            incremental_indexes=list(range(1, CBT_BACKUP_CHAIN_INCREMENTAL_COUNT + 1)),
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
        restored_vm_from_pull_chain,
    ):
        """
        Test that a full backup followed by multiple sequential incremental backups can restore
        the VM in pull mode.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Scratch PVC available for pull mode

        Steps:
            1. Perform a full backup in pull mode, wait until export is ready, and download it
            2. Delete the previous backup, write new test data to VM, perform an incremental
               backup in pull mode, wait until export is ready, and download it
            3. Repeat step 2 two more times
            4. Delete the original VM
            5. Restore the VM disk from the downloaded backups
            6. Start the restored VM

        Expected:
            - Every backup in the chain is ready for export and includes the boot disk, with the
              first backup typed Full and every following backup typed Incremental, and the
              restored VM boots with the original test data and the data from every incremental
              backup
        """
        expected_chain_length = 1 + CBT_BACKUP_CHAIN_INCREMENTAL_COUNT
        assert len(ready_pull_backup_chain.backups) == expected_chain_length, (
            f"Expected 1 full + {CBT_BACKUP_CHAIN_INCREMENTAL_COUNT} incremental backups, "
            f"got {len(ready_pull_backup_chain.backups)}"
        )
        for backup_index, (backup_name, backup_status) in enumerate(ready_pull_backup_chain.backups):
            expected_backup_type = CBT_BACKUP_TYPE_FULL if backup_index == 0 else CBT_BACKUP_TYPE_INCREMENTAL
            assert_backup_status_includes_volumes(
                backup_name=backup_name,
                backup_status=backup_status,
                expected_volume_names=[DV_DISK],
                expected_backup_type=expected_backup_type,
            )
        assert_restored_cbt_vm_data(
            vm=restored_vm_from_pull_chain,
            incremental_indexes=list(range(1, CBT_BACKUP_CHAIN_INCREMENTAL_COUNT + 1)),
        )


# Required at collection for storage_class_matrix__module__.
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-multi-disk", "data_disk_count": CBT_MULTI_DISK_DATA_DISK_COUNT}],
    indirect=True,
)
class TestMultipleDiskBackup:
    """
    Full backup and integrity restore for VMs with multiple disks.

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
        restored_vm_from_push_chain,
    ):
        """
        Test that a full backup in push mode completes and a multi-disk VM can be restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running CBT-enabled VM with a boot disk and two data disks
            - Test data written to all disks
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in push mode
            3. Wait for the backup to complete
            4. Delete the original VM
            5. Restore the boot disk and both data disks from the backup
            6. Start the restored VM

        Expected:
            - Full backup completes and includes the boot disk and all data disks, and the
              restored VM boots with the original test data on the boot disk and both data disks
        """
        data_disk_names = cbt_data_disk_volume_names(vm=restored_vm_from_push_chain)
        assert len(data_disk_names) == CBT_MULTI_DISK_DATA_DISK_COUNT, (
            f"Restored VM {restored_vm_from_push_chain.name} has data disks {data_disk_names}, "
            f"expected {CBT_MULTI_DISK_DATA_DISK_COUNT}"
        )
        full_backup = completed_push_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=full_backup.name,
            backup_status=full_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK, *data_disk_names],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_push_chain, data_disk_names=data_disk_names)

    @pytest.mark.polarion("CNV-16004")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_backup_multiple_disks_pull_mode(
        self,
        ready_pull_backup_chain,
        restored_vm_from_pull_chain,
    ):
        """
        Test that a full backup in pull mode can be exported and a multi-disk VM restored from it.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running CBT-enabled VM with a boot disk and two data disks
            - Test data written to all disks
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the VM
            2. Perform a full backup in pull mode
            3. Wait for the backup export to become ready and download every disk
            4. Delete the original VM
            5. Restore the boot disk and both data disks from the downloaded backup
            6. Start the restored VM

        Expected:
            - Backup export is ready and includes the boot disk and all data disks, and the
              restored VM boots with the original test data on the boot disk and both data disks
        """
        data_disk_names = cbt_data_disk_volume_names(vm=restored_vm_from_pull_chain)
        assert len(data_disk_names) == CBT_MULTI_DISK_DATA_DISK_COUNT, (
            f"Restored VM {restored_vm_from_pull_chain.name} has data disks {data_disk_names}, "
            f"expected {CBT_MULTI_DISK_DATA_DISK_COUNT}"
        )
        backup_name, backup_status = ready_pull_backup_chain.backups[0]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK, *data_disk_names],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_pull_chain, data_disk_names=data_disk_names)


@pytest.mark.special_infra
@pytest.mark.rwx_default_storage
# Required at collection for storage_class_matrix_rwx_matrix__module__.
@pytest.mark.usefixtures("rwx_storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-migrate", "storage_class_fixture": "rwx_storage_class_name_scope_module"}],
    indirect=True,
)
class TestBackupAfterLiveMigration:
    """
    Incremental backup and integrity restore after VM live migration.

    Preconditions:
        - Running VM with CBT enabled
        - VM disks on RWX backend PVC
        - At least two worker nodes available
        - Test data written to VM
        - Full backup completed before migration
    """

    @pytest.mark.polarion("CNV-16005")
    def test_incremental_backup_after_live_migration_push_mode(
        self,
        completed_push_backup_after_live_migration,
        restored_vm_from_push_after_live_migration,
    ):
        """
        Test that an incremental backup in push mode after live migration can restore the VM.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running CBT-enabled VM with disks on RWX storage
            - Test data written to the VM
            - Backup PVC available
            - Full backup completed in push mode

        Steps:
            1. Live migrate the VM to another node
            2. Wait for migration to complete
            3. Write new test data to VM
            4. Perform an incremental backup in push mode
            5. Wait for the backup to complete
            6. Delete the original VM
            7. Restore the VM disk from the full and incremental backups
            8. Start the restored VM

        Expected:
            - Incremental backup completes and includes the boot disk, and the restored VM
              boots with the original test data and the data written after migration
        """
        incremental_backup = completed_push_backup_after_live_migration[-1]
        assert_backup_status_includes_volumes(
            backup_name=incremental_backup.name,
            backup_status=incremental_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )
        assert_restored_cbt_vm_data(
            vm=restored_vm_from_push_after_live_migration,
            incremental_indexes=[1],
        )

    @pytest.mark.polarion("CNV-16006")
    def test_incremental_backup_after_live_migration_pull_mode(
        self,
        ready_pull_backup_after_live_migration,
        restored_vm_from_pull_after_live_migration,
    ):
        """
        Test that an incremental backup in pull mode after live migration can restore the VM.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running CBT-enabled VM with disks on RWX storage
            - Test data written to the VM
            - Scratch PVC available for pull mode
            - Full backup completed in pull mode
            - Full pull-mode backup export is deleted before migration
            - No active backup export during migration

        Steps:
            1. Download the full pull-mode backup and delete its export
            2. Live migrate the VM to another node
            3. Wait for migration to complete
            4. Write new test data to VM
            5. Perform an incremental backup in pull mode
            6. Wait for the backup export to become ready and download it
            7. Delete the original VM
            8. Restore the VM disk from the downloaded backups
            9. Start the restored VM

        Expected:
            - Incremental backup export is ready and includes the boot disk, and the restored
              VM boots with the original test data and the data written after migration
        """
        backup_name, backup_status = ready_pull_backup_after_live_migration.backups[-1]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
        )
        assert_restored_cbt_vm_data(
            vm=restored_vm_from_pull_after_live_migration,
            incremental_indexes=[1],
        )


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
    @pytest.mark.manual
    def test_backup_with_hotplugged_disk_push_mode_restore(self):
        """
        Test that a VM with hotplugged disk can be backed up (push mode) and restored with hotplugged disk data accessible.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

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
    @pytest.mark.manual
    def test_backup_with_hotplugged_disk_pull_mode_restore(self):
        """
        Test that a VM with hotplugged disk can be backed up (pull mode) and restored with hotplugged disk data accessible.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

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
    @pytest.mark.manual
    def test_backup_fails_when_storage_full_push_mode(self):
        """
        [NEGATIVE] Test that backup fails gracefully when backup PVC is full.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

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
    @pytest.mark.manual
    def test_backup_fails_when_storage_full_pull_mode(self):
        """
        [NEGATIVE] Test that backup fails gracefully when scratch PVC is full in pull mode.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

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


# Required at collection for storage_class_matrix__module__.
@pytest.mark.tier3
@pytest.mark.usefixtures("storage_class_name_scope_module")
class TestConcurrentBackups:
    """
    Concurrent full and incremental backups on multiple VMs, with integrity restore.

    Preconditions:
        - Five running VMs with CBT enabled
        - Test data written to each VM
        - A completed full backup on the three VMs that take an incremental backup
    """

    @pytest.mark.polarion("CNV-16011")
    def test_concurrent_backups_push_mode(
        self,
        completed_concurrent_push_backups,
        restored_vms_from_concurrent_push,
    ):
        """
        Test that simultaneous push-mode full and incremental backups all complete and restore.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Five running CBT-enabled VMs with test data written to each VM
            - A completed full backup on the three VMs that take an incremental backup
            - Backup PVC available for each VM

        Steps:
            1. Create a backup tracker and a backup PVC for each VM
            2. Complete a full backup on three of the VMs and write new test data to those VMs
            3. After step 2 finishes, start these backups together:
               - An incremental backup on the three VMs from step 2
               - A full backup on the other two
            4. Wait until every backup in that simultaneous set completes
            5. Delete each original VM, restore its disk from its backup chain, and start it

        Expected:
            - All five simultaneous backups complete and include the boot disk, three typed
              Incremental and two typed Full, and every restored VM boots with its test data
        """
        assert len(completed_concurrent_push_backups) == CBT_CONCURRENT_VM_COUNT, (
            f"Expected {CBT_CONCURRENT_VM_COUNT} simultaneous push backups, "
            f"got {len(completed_concurrent_push_backups)}"
        )
        assert len(restored_vms_from_concurrent_push) == CBT_CONCURRENT_VM_COUNT, (
            f"Expected {CBT_CONCURRENT_VM_COUNT} restored VMs, got {len(restored_vms_from_concurrent_push)}"
        )
        for backup_index, backup in enumerate(completed_concurrent_push_backups):
            assert_backup_status_includes_volumes(
                backup_name=backup.name,
                backup_status=backup.instance.to_dict()["status"],
                expected_volume_names=[DV_DISK],
                expected_backup_type=concurrent_backup_type(backup_index=backup_index),
            )
            incremental_indexes = (
                [backup_index + 1]
                if concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_INCREMENTAL
                else None
            )
            assert_restored_cbt_vm_data(
                vm=restored_vms_from_concurrent_push[backup_index],
                incremental_indexes=incremental_indexes,
            )

    @pytest.mark.polarion("CNV-16012")
    def test_concurrent_backups_pull_mode(
        self,
        ready_concurrent_pull_backups,
        restored_vms_from_concurrent_pull,
    ):
        """
        Test that simultaneous pull-mode full and incremental backups all export and restore.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Five running CBT-enabled VMs with test data written to each VM
            - A completed full backup on the three VMs that take an incremental backup
            - Scratch PVC available for each VM

        Steps:
            1. Create a backup tracker and a scratch PVC for each VM
            2. Complete a full backup on three of the VMs, download and delete those exports,
               and write new test data to those VMs
            3. After step 2 finishes, start these backups together:
               - An incremental backup on the three VMs from step 2
               - A full backup on the other two
            4. Wait until every backup in that simultaneous set is ready for export and
               download it
            5. Delete each original VM, restore its disk from the downloaded backups, and
               start it

        Expected:
            - All five simultaneous backups are ready for export and include the boot disk,
              three typed Incremental and two typed Full, and every restored VM boots with
              its test data
        """
        concurrent_backups = ready_concurrent_pull_backups.backups
        assert len(concurrent_backups) == CBT_CONCURRENT_VM_COUNT, (
            f"Expected {CBT_CONCURRENT_VM_COUNT} simultaneous pull backups, got {len(concurrent_backups)}"
        )
        assert len(restored_vms_from_concurrent_pull) == CBT_CONCURRENT_VM_COUNT, (
            f"Expected {CBT_CONCURRENT_VM_COUNT} restored VMs, got {len(restored_vms_from_concurrent_pull)}"
        )
        for backup_index, (backup_name, backup_status) in enumerate(concurrent_backups):
            assert_backup_status_includes_volumes(
                backup_name=backup_name,
                backup_status=backup_status,
                expected_volume_names=[DV_DISK],
                expected_backup_type=concurrent_backup_type(backup_index=backup_index),
            )
            incremental_indexes = (
                [backup_index + 1]
                if concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_INCREMENTAL
                else None
            )
            assert_restored_cbt_vm_data(
                vm=restored_vms_from_concurrent_pull[backup_index],
                incremental_indexes=incremental_indexes,
            )


# Required at collection for storage_class_matrix__module__.
@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.high_resource_vm
@pytest.mark.special_infra
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-win-full", "windows": True}],
    indirect=True,
)
class TestWindowsVMFullBackup:
    """
    Full backup and integrity restore for Windows VMs with persistent vTPM and EFI.

    Preconditions:
        - Running Windows VM with CBT enabled and persistent vTPM
        - Test data written to Windows VM
    """

    @pytest.mark.polarion("CNV-16013")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_windows_vm_full_backup_push_mode(
        self,
        completed_push_backup_chain,
        restored_vm_from_push_chain,
    ):
        """
        Test that a Windows VM full backup in push mode completes and the VM can be restored.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running Windows VM with CBT enabled and persistent vTPM
            - Backup PVC available

        Steps:
            1. Create a backup tracker for the Windows VM
            2. Perform a full backup in push mode
            3. Wait for the backup to complete
            4. Delete the original VM
            5. Restore the Windows boot disk from the backup
            6. Start the restored VM

        Expected:
            - Full backup completes and includes the boot disk, and the restored Windows VM
              boots with the original test data
        """
        full_backup = completed_push_backup_chain[0]
        assert_backup_status_includes_volumes(
            backup_name=full_backup.name,
            backup_status=full_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
            allow_extra_volumes=True,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_push_chain)

    @pytest.mark.polarion("CNV-16014")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 0}],
        indirect=True,
    )
    def test_windows_vm_full_backup_pull_mode(
        self,
        ready_pull_backup_chain,
        restored_vm_from_pull_chain,
    ):
        """
        Test that a Windows VM full backup in pull mode can be exported and the VM restored.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running Windows VM with CBT enabled and persistent vTPM
            - Scratch PVC available for pull mode

        Steps:
            1. Create a backup tracker for the Windows VM
            2. Perform a full backup in pull mode
            3. Wait for the backup export to become ready and download it
            4. Delete the original VM
            5. Restore the Windows boot disk from the downloaded backup
            6. Start the restored VM

        Expected:
            - Backup export is ready and includes the boot disk, and the restored Windows VM
              boots with the original test data
        """
        backup_name, backup_status = ready_pull_backup_chain.backups[0]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_FULL,
            allow_extra_volumes=True,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_pull_chain)


# Required at collection for storage_class_matrix__module__.
@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.high_resource_vm
@pytest.mark.special_infra
@pytest.mark.usefixtures("storage_class_name_scope_module")
@pytest.mark.parametrize(
    "vm_with_cbt_label",
    [{"name": "cbt-win-incr", "windows": True}],
    indirect=True,
)
class TestWindowsVMIncrementalBackup:
    """
    Incremental backup and integrity restore for Windows VMs with persistent vTPM and EFI.

    Preconditions:
        - Running Windows VM with CBT enabled and persistent vTPM
        - Full backup completed
        - Test data written to Windows VM
    """

    @pytest.mark.polarion("CNV-16015")
    @pytest.mark.parametrize(
        "completed_push_backup_chain",
        [{"incremental_count": 1}],
        indirect=True,
    )
    def test_windows_vm_incremental_backup_push_mode(
        self,
        completed_push_backup_chain,
        restored_vm_from_push_chain,
    ):
        """
        Test that a Windows VM incremental backup in push mode completes and the VM can be restored.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running Windows VM with CBT enabled and persistent vTPM
            - Backup PVC available
            - Full backup completed in push mode

        Steps:
            1. Write new test data to the Windows VM
            2. Perform an incremental backup in push mode
            3. Wait for the backup to complete
            4. Delete the original VM
            5. Restore the Windows boot disk from the full and incremental backups
            6. Start the restored VM

        Expected:
            - Incremental backup completes and includes the boot disk, and the restored Windows
              VM boots with the original test data and the data written before the incremental backup
        """
        incremental_backup = completed_push_backup_chain[-1]
        assert_backup_status_includes_volumes(
            backup_name=incremental_backup.name,
            backup_status=incremental_backup.instance.to_dict()["status"],
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
            allow_extra_volumes=True,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_push_chain, incremental_indexes=[1])

    @pytest.mark.polarion("CNV-16016")
    @pytest.mark.parametrize(
        "ready_pull_backup_chain",
        [{"incremental_count": 1}],
        indirect=True,
    )
    def test_windows_vm_incremental_backup_pull_mode(
        self,
        ready_pull_backup_chain,
        restored_vm_from_pull_chain,
    ):
        """
        Test that a Windows VM incremental backup in pull mode can be exported and the VM restored.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/cbt.md

        Preconditions:
            - Running Windows VM with CBT enabled and persistent vTPM
            - Scratch PVC available for pull mode

        Steps:
            1. Perform a full backup in pull mode, wait until export is ready, and download it
            2. Delete the full pull-mode backup
            3. Write new test data to the Windows VM
            4. Perform an incremental backup in pull mode
            5. Wait for the backup export to become ready and download it
            6. Delete the original VM
            7. Restore the Windows boot disk from the downloaded backups
            8. Start the restored VM

        Expected:
            - Incremental backup export is ready and includes the boot disk, and the restored
              Windows VM boots with the original test data and the data written before the
              incremental backup
        """
        backup_name, backup_status = ready_pull_backup_chain.backups[-1]
        assert_backup_status_includes_volumes(
            backup_name=backup_name,
            backup_status=backup_status,
            expected_volume_names=[DV_DISK],
            expected_backup_type=CBT_BACKUP_TYPE_INCREMENTAL,
            allow_extra_volumes=True,
        )
        assert_restored_cbt_vm_data(vm=restored_vm_from_pull_chain, incremental_indexes=[1])
