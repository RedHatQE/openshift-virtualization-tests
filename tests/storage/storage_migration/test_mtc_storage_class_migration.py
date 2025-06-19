import pytest
from pytest_testconfig import config as py_config

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS
from tests.storage.storage_migration.constants import (
    CONTENT,
    FILE_BEFORE_STORAGE_MIGRATION,
    STORAGE_CLASS_A,
    STORAGE_CLASS_B,
)
from tests.storage.storage_migration.utils import (
    verify_file_in_hotplugged_disk,
    verify_storage_migration_succeeded,
)
from utilities.virt import migrate_vm_and_verify

TESTS_CLASS_NAME_A_TO_B = "TestStorageClassMigrationAtoB"
TESTS_CLASS_NAME_B_TO_A = "TestStorageClassMigrationBtoA"
TESTS_CLASS_NAME_VOLUME_HOTPLUG = "TestStorageClassMigrationWithVolumeHotplug"


@pytest.mark.parametrize(
    "vms_for_storage_class_migration",
    [
        pytest.param(
            {
                "vms_fixtures": [
                    "vm_for_storage_class_migration_with_instance_type",
                    "vm_for_storage_class_migration_from_template_with_data_source",
                    "vm_for_storage_class_migration_from_template_with_dv",
                ]
            },
            id="source_a_target_b",
        )
    ],
    indirect=True,
)
class TestStorageClassMigrationAtoB:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_A_TO_B}::test_vm_storage_class_migration_a_to_b_running_vms")
    @pytest.mark.parametrize(
        "source_storage_class, target_storage_class, online_vms_for_storage_class_migration",
        [
            pytest.param(
                {"source_storage_class": py_config[STORAGE_CLASS_A]},
                {"target_storage_class": py_config[STORAGE_CLASS_B]},
                {"online_vm": [True, True, True]},  # Desired VM Running status for VMs in "vms_fixtures" list
                marks=pytest.mark.polarion("CNV-11500"),
                id="storage_migration_a_to_b_running_vms",
            )
        ],
        indirect=True,
    )
    def test_vm_storage_class_migration_a_to_b_running_vms(
        self,
        source_storage_class,
        target_storage_class,
        written_file_to_vms_before_migration,
        online_vms_for_storage_class_migration,
        vms_boot_time_before_storage_migration,
        storage_mig_plan,
        storage_mig_migration,
        deleted_old_dvs_of_online_vms,
    ):
        verify_storage_migration_succeeded(
            vms_boot_time_before_storage_migration=vms_boot_time_before_storage_migration,
            online_vms_for_storage_class_migration=online_vms_for_storage_class_migration,
            vms_with_written_file_before_migration=written_file_to_vms_before_migration,
            target_storage_class=target_storage_class,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_A_TO_B}::test_vm_storage_class_migration_a_to_b_running_vms"])
    @pytest.mark.polarion("CNV-11504")
    def test_migrate_vms_after_storage_migration(self, booted_vms_for_storage_class_migration):
        vms_failed_migration = {}
        for vm in booted_vms_for_storage_class_migration:
            try:
                migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
            except Exception as migration_exception:
                vms_failed_migration[vm.name] = migration_exception
        assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, data_volume_scope_class, "
    "vm_for_storage_class_migration_from_template_with_existing_dv, "
    "vms_for_storage_class_migration, online_vms_for_storage_class_migration",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_B]},
            {"target_storage_class": py_config[STORAGE_CLASS_A]},
            {
                "dv_name": "standalone-dv-fedora",
                "image": FEDORA_LATEST.get("image_path"),
                "storage_class": py_config[STORAGE_CLASS_B],
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            {
                "vm_name": "fedora-vm-with-existing-dv",
                "template_labels": FEDORA_LATEST_LABELS,
                "start_vm": False,
            },
            {
                "vms_fixtures": [
                    "vm_for_storage_class_migration_with_instance_type",
                    "vm_for_storage_class_migration_from_template_with_existing_dv",
                ]
            },
            {"online_vm": [False, True]},  # Desired VM Running status for VMs in "vms_fixtures" list
            id="storage_migration_a_to_b_running_and_stopped_vms",
        )
    ],
    indirect=True,
)
class TestStorageClassMigrationBtoA:
    @pytest.mark.polarion("CNV-11501")
    def test_vm_storage_class_migration_b_to_a_with_running_and_stopped_vms(
        self,
        source_storage_class,
        target_storage_class,
        data_volume_scope_class,
        vm_for_storage_class_migration_from_template_with_existing_dv,
        written_file_to_vms_before_migration,
        online_vms_for_storage_class_migration,
        vms_boot_time_before_storage_migration,
        storage_mig_plan,
        storage_mig_migration,
        deleted_old_dvs_of_online_vms,
        deleted_old_dvs_of_stopped_vms,
    ):
        verify_storage_migration_succeeded(
            vms_boot_time_before_storage_migration=vms_boot_time_before_storage_migration,
            online_vms_for_storage_class_migration=online_vms_for_storage_class_migration,
            vms_with_written_file_before_migration=written_file_to_vms_before_migration,
            target_storage_class=target_storage_class,
        )


@pytest.mark.parametrize(
    "source_storage_class, vms_for_storage_class_migration",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"vms_fixtures": ["vm_for_storage_class_migration_with_hotplugged_volume"]},
            id="mig_volume_hotplug_source_a_target_b",
        )
    ],
    indirect=True,
)
class TestStorageClassMigrationWithVolumeHotplug:
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME_VOLUME_HOTPLUG}::test_vm_storage_class_migration_with_hotplugged_volume"
    )
    @pytest.mark.parametrize(
        "target_storage_class, online_vms_for_storage_class_migration",
        [
            pytest.param(
                {"target_storage_class": py_config[STORAGE_CLASS_B]},
                {"online_vm": [True]},  # Desired VM Running status for VMs in "vms_fixtures" list
                marks=pytest.mark.polarion("CNV-11496"),
                id="storage_migration_a_to_b_volume_hotplug_vms",
            )
        ],
        indirect=True,
    )
    def test_vm_storage_class_migration_with_hotplugged_volume(
        self,
        source_storage_class,
        target_storage_class,
        written_file_to_the_mounted_hotplugged_disk,
        written_file_to_vms_before_migration,
        online_vms_for_storage_class_migration,
        vms_boot_time_before_storage_migration,
        storage_mig_plan,
        storage_mig_migration,
        deleted_old_dvs_of_online_vms,
    ):
        verify_storage_migration_succeeded(
            vms_boot_time_before_storage_migration=vms_boot_time_before_storage_migration,
            online_vms_for_storage_class_migration=online_vms_for_storage_class_migration,
            vms_with_written_file_before_migration=written_file_to_vms_before_migration,
            target_storage_class=target_storage_class,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VOLUME_HOTPLUG}::test_vm_storage_class_migration_with_hotplugged_volume"]
    )
    @pytest.mark.polarion("CNV-12002")
    def test_hotplugged_volume_data_after_storage_migration(
        self, vms_for_storage_class_migration, written_file_to_the_mounted_hotplugged_disk
    ):
        verify_file_in_hotplugged_disk(
            vm=written_file_to_the_mounted_hotplugged_disk,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_VOLUME_HOTPLUG}::test_vm_storage_class_migration_with_hotplugged_volume"]
    )
    @pytest.mark.polarion("CNV-11966")
    def test_migrate_vm_with_hotplugged_volume_after_storage_migration(
        self, source_storage_class, booted_vms_for_storage_class_migration
    ):
        vms_failed_migration = {}
        for vm in booted_vms_for_storage_class_migration:
            try:
                migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
            except Exception as migration_exception:
                vms_failed_migration[vm.name] = migration_exception
        assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"
