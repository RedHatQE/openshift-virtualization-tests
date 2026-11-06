"""
Offline VM Storage Migration Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md
Jira: https://issues.redhat.com/browse/CNV-77501 # <skip-jira-utils-check>
"""

import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_A, STORAGE_CLASS_B
from tests.storage.storage_migration.constants import (
    CONTENT,
    DELETE_SOURCE,
    FILE_BEFORE_STORAGE_MIGRATION,
    KEEP_SOURCE,
)
from tests.storage.storage_migration.utils import (
    get_vm_volume_node,
    mount_hotplugged_disks,
    verify_files_in_hotplugged_disks,
    verify_source_dvs_deleted,
    verify_source_dvs_exist,
    verify_vm_dv_names_changed,
    verify_vm_dv_names_unchanged,
    verify_vm_pending_until_storage_migration_completed,
    verify_vm_pvcs_volume_mode,
    verify_vm_storage_class_updated,
    verify_vms_boot_time_after_storage_migration,
    wait_for_offline_storage_migration_completed,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants.pytest import QUARANTINED
from utilities.virt import running_vm

BLOCK = DataVolume.VolumeMode.BLOCK
FILESYSTEM = DataVolume.VolumeMode.FILE


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        ),
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_B]},
            {"target_storage_class": py_config[STORAGE_CLASS_A]},
            id="source_b_target_a",
        ),
    ],
    indirect=True,
)
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

    @pytest.mark.parametrize(
        "source_volume_mode, target_volume_mode",
        [
            pytest.param(BLOCK, BLOCK, id="block_to_block"),
            pytest.param(FILESYSTEM, FILESYSTEM, id="file_to_file"),
            pytest.param(BLOCK, FILESYSTEM, id="block_to_file"),
            pytest.param(FILESYSTEM, BLOCK, id="file_to_block"),
        ],
    )
    @pytest.mark.polarion("CNV-16796")
    @pytest.mark.usefixtures("volume_mode_offline_mig_migration")
    def test_offline_vm_storage_migration_across_volume_modes(
        self,
        target_storage_class,
        target_volume_mode,
        stopped_vm_with_volume_mode_for_scmig,
    ):
        """
        Test that offline VM storage migration completes successfully and preserves data
        across volume mode combinations between different storage classes.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

        Preconditions:
            - Stopped VM with a data disk on the source storage class using the source volume mode
            - File written to the VM data disk with known content

        Steps:
            1. Create a storage migration plan for the stopped VM targeting the destination storage class and volume mode
            2. Execute the storage migration and wait for completion
            3. Verify the migrated disk uses the target storage class and volume mode
            4. Start the VM after migration completes
            5. Read the file content from the VM data disk

        Expected:
            - Migration plan status is "Succeeded"
            - Migrated disk uses the target storage class and volume mode
            - VM boots successfully after migration
            - File content equals the pre-migration written data
        """
        verify_vm_storage_class_updated(
            vm=stopped_vm_with_volume_mode_for_scmig, target_storage_class=target_storage_class
        )
        verify_vm_pvcs_volume_mode(vm=stopped_vm_with_volume_mode_for_scmig, volume_mode=target_volume_mode)
        stopped_vm_with_volume_mode_for_scmig.start(wait=True)
        running_vm(vm=stopped_vm_with_volume_mode_for_scmig)
        check_file_in_vm(
            vm=stopped_vm_with_volume_mode_for_scmig,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, combined_mode_mig_plan",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestMixedOfflineOnlineStorageMigration:
    """
    Tests for storage migration with a migration plan containing both offline and running VMs.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM on the source storage class
        - Running VM on the source storage class, boot time recorded before migration
    """

    @pytest.mark.polarion("CNV-16797")
    def test_mixed_offline_online_vm_storage_migration(
        self,
        target_storage_class,
        running_vm_for_scmig_test_first_ns,
        stopped_vm_for_scmig_test_first_ns,
        running_vm_for_scmig_test_boot_time,
        combined_mode_mig_migration_in_progress,
    ):
        """
        Test that storage migration completes for a plan containing both offline and running VMs
        while each VM preserves its original state.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        assert running_vm_for_scmig_test_first_ns.ready, (
            f"VM {running_vm_for_scmig_test_first_ns.name} is not running while storage migration is in progress"
        )
        wait_for_offline_storage_migration_completed(mig_migration=combined_mode_mig_migration_in_progress)
        verify_vm_storage_class_updated(
            vm=stopped_vm_for_scmig_test_first_ns, target_storage_class=target_storage_class
        )
        assert (
            stopped_vm_for_scmig_test_first_ns.printable_status == stopped_vm_for_scmig_test_first_ns.Status.STOPPED
        ), (
            f"VM {stopped_vm_for_scmig_test_first_ns.name} is not stopped after storage migration, "
            f"status: {stopped_vm_for_scmig_test_first_ns.printable_status}"
        )
        verify_vm_storage_class_updated(
            vm=running_vm_for_scmig_test_first_ns, target_storage_class=target_storage_class
        )
        verify_vms_boot_time_after_storage_migration(
            vm_list=[running_vm_for_scmig_test_first_ns],
            initial_boot_time={running_vm_for_scmig_test_first_ns.name: running_vm_for_scmig_test_boot_time},
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestOfflineStorageMigrationCleanupPolicy:
    """
    Tests for source volume cleanup policy during offline VM storage migration.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - File written to the VM data disk with known content
        - Source volume identifier recorded before migration
    """

    @pytest.mark.parametrize(
        "offline_vm_mig_plan",
        [pytest.param({"retention_policy": KEEP_SOURCE}, id="keep_source")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16798")
    @pytest.mark.usefixtures("offline_vm_mig_migration")
    def test_source_volumes_retained_after_offline_migration(
        self,
        stopped_vm_with_written_file_for_scmig,
        stopped_vm_with_written_file_source_dv_names,
    ):
        """
        Test that source volumes are retained after offline VM storage migration
        when cleanup policy is set to retain.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        verify_source_dvs_exist(
            vm=stopped_vm_with_written_file_for_scmig, source_dv_names=stopped_vm_with_written_file_source_dv_names
        )
        stopped_vm_with_written_file_for_scmig.start(wait=True)
        running_vm(vm=stopped_vm_with_written_file_for_scmig)
        check_file_in_vm(
            vm=stopped_vm_with_written_file_for_scmig,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )

    @pytest.mark.parametrize(
        "offline_vm_mig_plan",
        [pytest.param({"retention_policy": DELETE_SOURCE}, id="delete_source")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-16799")
    @pytest.mark.usefixtures("offline_vm_mig_migration")
    def test_source_volumes_deleted_after_offline_migration(
        self,
        stopped_vm_with_written_file_for_scmig,
        stopped_vm_with_written_file_source_dv_names,
    ):
        """
        Test that source volumes are deleted after offline VM storage migration
        when cleanup policy is set to delete.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        verify_source_dvs_deleted(
            vm=stopped_vm_with_written_file_for_scmig, source_dv_names=stopped_vm_with_written_file_source_dv_names
        )
        stopped_vm_with_written_file_for_scmig.start(wait=True)
        running_vm(vm=stopped_vm_with_written_file_for_scmig)
        check_file_in_vm(
            vm=stopped_vm_with_written_file_for_scmig,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestOfflineVMStorageMigrationWithHotplugDisks:
    """
    Tests for offline VM storage migration with hotplug disks attached.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with boot disk and hotplug disks on the source storage class
        - File written to each disk with known content
    """

    @pytest.mark.polarion("CNV-16800")
    @pytest.mark.usefixtures("hotplug_offline_mig_migration")
    def test_offline_vm_with_hotplug_disks_storage_migration(
        self,
        target_storage_class,
        blank_disk_dvs_for_storage_migration,
        stopped_vm_with_written_files_on_hotplugged_disks,
    ):
        """
        Test that offline VM storage migration migrates all disks including hotplug disks.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        verify_vm_storage_class_updated(
            vm=stopped_vm_with_written_files_on_hotplugged_disks, target_storage_class=target_storage_class
        )
        stopped_vm_with_written_files_on_hotplugged_disks.start(wait=True)
        running_vm(vm=stopped_vm_with_written_files_on_hotplugged_disks)
        check_file_in_vm(
            vm=stopped_vm_with_written_files_on_hotplugged_disks,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )
        # Hotplugged disk mounts do not persist across VM restarts
        mount_hotplugged_disks(
            vm=stopped_vm_with_written_files_on_hotplugged_disks,
            hotplug_volume_names=[dv.name for dv in blank_disk_dvs_for_storage_migration],
        )
        verify_files_in_hotplugged_disks(
            vm=stopped_vm_with_written_files_on_hotplugged_disks,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, offline_vm_mig_plan",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_A]},
            {},
            id="source_a_target_a",
        ),
    ],
    indirect=True,
)
class TestOfflineVMSameClassMigrationAcrossNodes:
    """
    Tests for offline VM storage migration between nodes using the same storage class (HPP to HPP).

    Preconditions:
        - Node-local (HPP) storage class available on the cluster
        - At least two schedulable worker nodes
        - Stopped VM with a data disk on the HPP storage class
        - File written to the VM data disk with known content
        - Source volume node and identifier recorded before migration
    """

    @pytest.mark.special_infra
    @pytest.mark.tier3
    @pytest.mark.polarion("CNV-16801")
    @pytest.mark.usefixtures("hpp_node_to_node_mig_migration")
    def test_offline_vm_same_class_hpp_migration_across_nodes(
        self,
        stopped_vm_with_written_file_for_scmig,
        stopped_vm_with_written_file_source_dv_names,
        source_volume_node_for_scmig,
    ):
        """
        Test that offline VM storage migration from HPP to HPP across different nodes completes
        successfully, the VM references the new volume on a different node, and guest data is preserved.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

        Preconditions:
            - Stopped VM with a data disk on the HPP storage class
            - File written to the VM data disk with known content
            - Source volume node and identifier recorded before migration

        Steps:
            1. Create a storage migration plan for the stopped VM targeting the same HPP storage class
            2. Make the source node unschedulable so the migrated volume is provisioned on a different node
            3. Execute the storage migration and wait for completion
            4. Verify the VM disk references point to the new migrated volume on a different node
            5. Start the VM after migration completes
            6. Read the file content from the VM data disk

        Expected:
            - Migration plan status is "Succeeded"
            - VM disk references point to the new volume located on a different node than the source
            - VM boots successfully after migration and file content equals the pre-migration written data
        """
        verify_vm_dv_names_changed(
            vm=stopped_vm_with_written_file_for_scmig, original_dv_names=stopped_vm_with_written_file_source_dv_names
        )
        target_volume_node = get_vm_volume_node(vm=stopped_vm_with_written_file_for_scmig)
        assert target_volume_node and target_volume_node != source_volume_node_for_scmig, (
            f"Migrated volume for VM {stopped_vm_with_written_file_for_scmig.name} did not move to a different node. "
            f"Source node: {source_volume_node_for_scmig}, target node: {target_volume_node}"
        )
        stopped_vm_with_written_file_for_scmig.start(wait=True)
        running_vm(vm=stopped_vm_with_written_file_for_scmig)
        check_file_in_vm(
            vm=stopped_vm_with_written_file_for_scmig,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )


@pytest.mark.parametrize(
    "source_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            id="source_a",
        ),
    ],
    indirect=True,
)
class TestOfflineVMStorageMigrationFailureRollback:
    """
    Tests for offline VM rollback behavior on storage migration failure.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - VM disk references recorded before migration
        - Source volume identifier recorded before migration
        - Storage migration configured to trigger a failure during migration
    """

    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Not clarified Failing migration cases, wait for product clarification, CNV-98407",
        run=False,
    )
    @pytest.mark.polarion("CNV-16802")
    @pytest.mark.usefixtures("offline_failure_mig_migration")
    def test_offline_vm_rollback_on_migration_failure(
        self,
        stopped_vm_for_scmig_test_first_ns,
        stopped_vm_for_scmig_test_source_dvs,
    ):
        """
        [NEGATIVE] Test that offline VM disk references remain unchanged and the source volume
        is preserved when storage migration fails.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

        Preconditions:
            - Stopped VM with a data disk on the source storage class
            - VM disk references recorded before migration
            - Source volume identifier recorded before migration
            - Storage migration configured to trigger a failure during migration

        Steps:
            1. Create a storage migration plan for the stopped VM
            2. Execute the storage migration and wait for it to fail
            3. Verify VM disk references after migration failure
            4. Verify the source volume still exists after migration failure

        Expected:
            - Migration plan status is "Failed"
            - VM disk references remain unchanged pointing to the original storage and the source
              volume is preserved regardless of cleanup policy
        """
        verify_vm_dv_names_unchanged(
            vm=stopped_vm_for_scmig_test_first_ns, expected_dv_names=stopped_vm_for_scmig_test_source_dvs
        )
        verify_source_dvs_exist(
            vm=stopped_vm_for_scmig_test_first_ns, source_dv_names=stopped_vm_for_scmig_test_source_dvs
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, offline_vm_mig_plan",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestVMStartDuringStorageMigration:
    """
    Tests for VM start behavior during an in-progress offline storage migration.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM with a data disk on the source storage class
        - File written to the VM data disk with known content
    """

    @pytest.mark.polarion("CNV-16803")
    def test_vm_start_during_offline_storage_migration(
        self,
        target_storage_class,
        offline_vm_mig_migration_in_progress,
        started_vm_during_offline_scmig,
    ):
        """
        Test that starting a stopped VM during storage migration succeeds
        and the VM waits for migration completion before becoming ready.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        verify_vm_pending_until_storage_migration_completed(
            vm=started_vm_during_offline_scmig, mig_migration=offline_vm_mig_migration_in_progress
        )
        running_vm(vm=started_vm_during_offline_scmig)
        verify_vm_storage_class_updated(vm=started_vm_during_offline_scmig, target_storage_class=target_storage_class)
        check_file_in_vm(
            vm=started_vm_during_offline_scmig,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, combined_mode_mig_plan",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {},
            id="source_a_target_b",
        ),
    ],
    indirect=True,
)
class TestCancelInProgressStorageMigration:
    """
    Tests for cancellation of in-progress storage migration for offline and online VMs.

    Preconditions:
        - Source and target storage classes available
        - Stopped VM on the source storage class with a sufficiently large disk
        - Running VM on the source storage class with a sufficiently large disk
        - VM disk references recorded before migration
    """

    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Canceled state is not set when a running migration is deleted, "
        "functionality not covered yet, CNV-95502",
        run=False,
    )
    @pytest.mark.polarion("CNV-16804")
    @pytest.mark.usefixtures("cancelled_combined_mode_mig_migration")
    def test_cancel_in_progress_storage_migration(
        self,
        running_vm_for_scmig_test_first_ns,
        stopped_vm_for_scmig_test_first_ns,
        running_vm_for_scmig_test_source_dvs,
        stopped_vm_for_scmig_test_source_dvs,
        running_vm_for_scmig_test_boot_time,
    ):
        """
        Test that cancelling an in-progress storage migration preserves original VM state
        for both offline and online VMs.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/storage_mig_offline.md

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
        verify_vm_dv_names_unchanged(
            vm=stopped_vm_for_scmig_test_first_ns, expected_dv_names=stopped_vm_for_scmig_test_source_dvs
        )
        verify_vm_dv_names_unchanged(
            vm=running_vm_for_scmig_test_first_ns, expected_dv_names=running_vm_for_scmig_test_source_dvs
        )
        assert running_vm_for_scmig_test_first_ns.ready, (
            f"VM {running_vm_for_scmig_test_first_ns.name} is not running after storage migration cancellation"
        )
        verify_vms_boot_time_after_storage_migration(
            vm_list=[running_vm_for_scmig_test_first_ns],
            initial_boot_time={running_vm_for_scmig_test_first_ns.name: running_vm_for_scmig_test_boot_time},
        )
        verify_source_dvs_exist(
            vm=stopped_vm_for_scmig_test_first_ns, source_dv_names=stopped_vm_for_scmig_test_source_dvs
        )
        verify_source_dvs_exist(
            vm=running_vm_for_scmig_test_first_ns, source_dv_names=running_vm_for_scmig_test_source_dvs
        )
