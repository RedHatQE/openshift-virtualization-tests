import logging

import pytest
from pytest_testconfig import config as py_config

from tests.storage.storage_migration.utils import CONTENT, FILE_BEFORE_STORAGE_MIGRATION, check_file_in_vm
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)

TESTS_CLASS_NAME_A_TO_B = "TestStorageClassMigrationAtoB"
TESTS_CLASS_NAME_B_TO_A = "TestStorageClassMigrationBtoA"


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, vms_for_storage_class_migration",
    [
        pytest.param(
            {"source_storage_class": py_config["storage_class_for_storage_migration_a"]},
            {"target_storage_class": py_config["storage_class_for_storage_migration_b"]},
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
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_A_TO_B}::test_vm_storage_class_migration_a_to_b")
    @pytest.mark.polarion("CNV-")
    def test_vm_storage_class_migration_a_to_b(
        self,
        source_storage_class,
        running_vms_for_storage_class_migration,
        written_file_to_vms_before_migration,
        storage_mig_plan,
        storage_mig_migration,
        deleted_completed_virt_launcher_source_pod,
        deleted_old_dv,
    ):
        for vm in running_vms_for_storage_class_migration:
            check_file_in_vm(
                vm=vm,
                file_name=FILE_BEFORE_STORAGE_MIGRATION,
                file_content=CONTENT,
            )

    @pytest.mark.polarion("CNV-")
    def test_migrate_vms_after_storage_migration(self, running_vms_for_storage_class_migration):
        for vm in running_vms_for_storage_class_migration:
            migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class, vms_for_storage_class_migration",
    [
        pytest.param(
            {"source_storage_class": py_config["storage_class_for_storage_migration_b"]},
            {"target_storage_class": py_config["storage_class_for_storage_migration_a"]},
            {"vms_fixtures": ["vm_for_storage_class_migration_with_instance_type"]},
            id="source_b_target_a",
        )
    ],
    indirect=True,
)
class TestStorageClassMigrationBtoA:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_B_TO_A}::test_vm_storage_class_migration_b_to_a")
    @pytest.mark.polarion("CNV-")
    def test_vm_storage_class_migration_b_to_a(
        self,
        source_storage_class,
        running_vms_for_storage_class_migration,
        written_file_to_vms_before_migration,
        storage_mig_plan,
        storage_mig_migration,
        deleted_completed_virt_launcher_source_pod,
        deleted_old_dv,
    ):
        for vm in running_vms_for_storage_class_migration:
            check_file_in_vm(
                vm=vm,
                file_name=FILE_BEFORE_STORAGE_MIGRATION,
                file_content=CONTENT,
            )
