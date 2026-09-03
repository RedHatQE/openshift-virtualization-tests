"""
Offline VM Storage Migration Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md
Jira: https://issues.redhat.com/browse/CNV-77501 # <skip-jira-utils-check>
"""

import pytest


class TestOfflineVMStorageMigrationVolumeModes:
    """
    Tests for offline VM storage migration across volume mode combinations.

    Parametrize:
        - storage_class_direction:
            - Storage class A to storage class B
            - Storage class B to storage class A
        - volume_mode:
            - Block-to-Block
            - File-to-File
            - Block-to-File
            - File-to-Block

    Preconditions:
        - Source and target storage classes available on the cluster
        - Stopped VM with a data disk on the source storage class using the source volume mode
        - File written to the VM data disk with known content
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16796")
    def test_offline_vm_storage_migration_across_volume_modes(self):
        """
        Test that offline VM storage migration completes successfully and preserves data
        across volume mode combinations between different storage classes.

        Preconditions:
            - Stopped VM with a data disk on the source storage class using the source volume mode
            - File written to the VM data disk with known content

        Steps:
            1. Create a storage migration plan for the stopped VM targeting the destination storage class and volume mode
            2. Execute the storage migration and wait for completion
            3. Start the VM after migration completes
            4. Read the file content from the VM data disk

        Expected:
            - Migration plan status is "Succeeded"
            - VM boots successfully after migration
            - File content equals the pre-migration written data
        """


class TestMixedOfflineOnlineStorageMigration:
    """
    Tests for storage migration with a migration plan containing both offline and running VMs.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM on the source storage class
        - Running VM on the source storage class, boot time recorded before migration
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16797")
    def test_mixed_offline_online_vm_storage_migration(self):
        """
        Test that storage migration completes for a plan containing both offline and running VMs
        while each VM preserves its original state.

        Preconditions:
            - Stopped VM on the source storage class
            - Running VM on the source storage class, boot time recorded before migration

        Steps:
            1. Create a storage migration plan including both the stopped VM and the running VM
            2. Execute the storage migration
            3. Verify the running VM remains running while migration is in progress
            4. Wait for migration to complete
            5. Verify all VMs point to the target storage class
            6. Verify each VM preserved its original state after migration

        Expected:
            - Migration plan status is "Succeeded"
            - Stopped VM disk references point to the target storage class and VM remains stopped
            - Running VM disk references point to the target storage class and VM remained running throughout without restart
        """


class TestOfflineStorageMigrationCleanupPolicy:
    """
    Tests for source volume cleanup policy during offline VM storage migration.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - File written to the VM data disk with known content
        - Source volume identifier recorded before migration
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16798")
    def test_source_volumes_retained_after_offline_migration(self):
        """
        Test that source volumes are retained after offline VM storage migration
        when cleanup policy is set to retain.

        Preconditions:
            - Stopped VM with a data disk on the source storage class
            - File written to the VM data disk with known content
            - Source volume identifier recorded before migration

        Steps:
            1. Create a storage migration plan with cleanup policy set to retain
            2. Execute the storage migration and wait for completion
            3. Check whether the source volumes still exist
            4. Start the VM after migration completes
            5. Read the file content from the VM data disk

        Expected:
            - Source volumes exist after migration completes
            - File content equals the pre-migration written data
        """

    @pytest.mark.polarion("CNV-16799")
    def test_source_volumes_deleted_after_offline_migration(self):
        """
        Test that source volumes are deleted after offline VM storage migration
        when cleanup policy is set to delete.

        Preconditions:
            - Stopped VM with a data disk on the source storage class
            - File written to the VM data disk with known content
            - Source volume identifier recorded before migration

        Steps:
            1. Create a storage migration plan with cleanup policy set to delete
            2. Execute the storage migration and wait for completion
            3. Check whether the source volumes still exist
            4. Start the VM after migration completes
            5. Read the file content from the VM data disk

        Expected:
            - Source volumes do not exist after migration completes
            - File content equals the pre-migration written data
        """


class TestOfflineVMStorageMigrationWithHotplugDisks:
    """
    Tests for offline VM storage migration with hotplug disks attached.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with boot disk and hotplug disks on the source storage class
        - File written to each disk with known content
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16800")
    def test_offline_vm_with_hotplug_disks_storage_migration(self):
        """
        Test that offline VM storage migration migrates all disks including hotplug disks.

        Preconditions:
            - Stopped VM with boot disk and hotplug disks on the source storage class
            - File written to each disk with known content

        Steps:
            1. Create a storage migration plan for the stopped VM targeting the destination storage class
            2. Execute the storage migration and wait for completion
            3. Start the VM after migration completes
            4. Verify all disks including hotplug disks are accessible and data is intact

        Expected:
            - Migration plan status is "Succeeded"
            - All disks including hotplug disks are migrated to the target storage class
            - VM boots successfully with all disks accessible and file content unchanged
        """


class TestOfflineVMStorageMigrationFailureRollback:
    """
    Tests for offline VM rollback behavior on storage migration failure.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - VM disk references recorded before migration
        - Storage migration configured to trigger a failure during migration
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16802")
    def test_offline_vm_rollback_on_migration_failure(self):
        """
        [NEGATIVE] Test that offline VM disk references remain unchanged when storage migration fails.

        Preconditions:
            - Stopped VM with a data disk on the source storage class
            - VM disk references recorded before migration
            - Storage migration configured to trigger a failure during migration

        Steps:
            1. Create a storage migration plan for the stopped VM
            2. Execute the storage migration and wait for it to fail
            3. Verify VM disk references after migration failure

        Expected:
            - Migration plan status is "Failed"
            - VM disk references remain unchanged pointing to the original storage
        """


class TestVMStartDuringStorageMigration:
    """
    Tests for VM start behavior during an in-progress offline storage migration.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - File written to the VM data disk with known content
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16803")
    def test_vm_start_during_offline_storage_migration(self):
        """
        Test that starting a stopped VM during storage migration succeeds
        and the VM waits for migration completion before becoming ready.

        Preconditions:
            - Stopped VM with a data disk on the source storage class
            - File written to the VM data disk with known content

        Steps:
            1. Create a storage migration plan for the stopped VM
            2. Execute the storage migration
            3. Start the VM while migration is in progress
            4. Verify VM state during migration
            5. Wait for migration to complete
            6. Read the file content from the VM data disk

        Expected:
            - Migration plan status is "Succeeded"
            - VM remains in a pending state during migration and becomes ready only after migration completes
            - VM disk references point to the target storage class
            - File content equals the pre-migration written data
        """


class TestCancelInProgressStorageMigration:
    """
    Tests for cancellation of in-progress storage migration for offline and online VMs.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM on the source storage class with a sufficiently large disk
        - Running VM on the source storage class with a sufficiently large disk
        - VM disk references recorded before migration
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16804")
    def test_cancel_in_progress_storage_migration(self):
        """
        Test that cancelling an in-progress storage migration preserves original VM state
        for both offline and online VMs.

        Preconditions:
            - Stopped VM on the source storage class with a sufficiently large disk
            - Running VM on the source storage class with a sufficiently large disk
            - VM disk references recorded before migration

        Steps:
            1. Create a storage migration plan with default cleanup policy (keepSource) for both VMs
            2. Execute the storage migration
            3. Cancel the migration while it is actively in progress
            4. Verify VM state and disk references after cancellation

        Expected:
            - Migration plan status is "Canceled"
            - VM disk references remain unchanged pointing to the original storage
            - Running VM remains running throughout the cancellation
            - Source volumes are preserved
        """
