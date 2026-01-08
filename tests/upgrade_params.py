from pytest_testconfig import config as py_config

from utilities.constants import EUS

UPGRADE_PACKAGE_NAME = "tests/install_upgrade_operators/product_upgrade"

if py_config["upgraded_product"] == EUS:
    upgrade_class = "TestEUSToEUSUpgrade"
    test_name = "test_eus_upgrade_process"
    file_name = f"{UPGRADE_PACKAGE_NAME}/test_eus_upgrade.py"
else:
    upgrade_class = "TestUpgrade"
    upgrade_source_suffix = "_production_source" if py_config["cnv_source"] == "production" else ""
    test_name = f"test{upgrade_source_suffix}_{py_config['upgraded_product']}_upgrade_process"
    file_name = f"{UPGRADE_PACKAGE_NAME}/test_upgrade.py"

IUO_UPGRADE_TEST_ORDERING_NODE_ID = IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID = f"{file_name}::{upgrade_class}::{test_name}"

IUO_CNV_ALERT_ORDERING_NODE_ID = (
    "tests/install_upgrade_operators/product_upgrade/test_upgrade_iuo.py::TestUpgradeIUO::"
    "test_alerts_fired_during_upgrade"
)
VIRT_NODE_ID_PREFIX = "tests/virt/upgrade/test_upgrade_virt.py::TestUpgradeVirt"
IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID = f"{VIRT_NODE_ID_PREFIX}::test_vmi_pod_image_updates_after_upgrade_optin"
STORAGE_NODE_ID_PREFIX = "tests/storage/upgrade/test_upgrade_storage.py::TestUpgradeStorage"
SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE = f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_restore_create_after_upgrade"
HOTPLUG_VM_AFTER_UPGRADE_NODE_ID = f"{STORAGE_NODE_ID_PREFIX}::test_vm_with_hotplug_after_upgrade"
SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID = f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_restore_check_after_upgrade"
CDI_SCRATCH_PRESERVE_NODE_ID = f"{STORAGE_NODE_ID_PREFIX}::test_cdiconfig_scratch_preserved_after_upgrade"
SCALE_NODE_ID_PREFIX = "tests/scale/test_upgrade_scale.py::TestUpgradeScale"
SCALE_VM_LOAD_RUNNING_AFTER_UPGRADE_ID = f"{SCALE_NODE_ID_PREFIX}::test_load_running_after_upgrade"
