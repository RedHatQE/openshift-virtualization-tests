from functools import cache

from pytest_testconfig import config as py_config

UPGRADE_PACKAGE_NAME = "tests/install_upgrade_operators/product_upgrade"
EUS = "eus"
OCP_CNV = "ocp_cnv"

# Static node ID prefixes and constants that don't depend on py_config
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

# Lazy attribute names - computed on first access when py_config is populated
_LAZY_ATTRS = frozenset({
    "OCP_PHASE_NODE_ID",
    "CNV_PHASE_NODE_ID",
    "IUO_UPGRADE_TEST_ORDERING_NODE_ID",
    "IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID",
})


@cache
def _compute_upgrade_params() -> dict[str, str | None]:
    """
    Compute upgrade parameters based on py_config.

    Called lazily on first access after pytest has initialized py_config.

    Returns:
        Dictionary containing computed node IDs for upgrade tests.
    """
    upgraded_product = py_config.get("upgraded_product", "")

    ocp_phase_node_id: str | None = None
    cnv_phase_node_id: str | None = None

    if upgraded_product == EUS:
        upgrade_class = "TestEUSToEUSUpgrade"
        test_name = "test_eus_upgrade_process"
        file_name = f"{UPGRADE_PACKAGE_NAME}/test_eus_upgrade.py"
        node_id = f"{file_name}::{upgrade_class}::{test_name}"
        return {
            "OCP_PHASE_NODE_ID": ocp_phase_node_id,
            "CNV_PHASE_NODE_ID": cnv_phase_node_id,
            "IUO_UPGRADE_TEST_ORDERING_NODE_ID": node_id,
            "IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID": node_id,
        }

    if upgraded_product == OCP_CNV:
        upgrade_class = "TestOCPCNVCombinedUpgrade"
        file_name = f"{UPGRADE_PACKAGE_NAME}/test_ocp_cnv_combined_upgrade.py"
        ocp_phase_node_id = f"{file_name}::{upgrade_class}::test_ocp_upgrade_phase"
        cnv_phase_node_id = f"{file_name}::{upgrade_class}::test_cnv_upgrade_phase"
        return {
            "OCP_PHASE_NODE_ID": ocp_phase_node_id,
            "CNV_PHASE_NODE_ID": cnv_phase_node_id,
            "IUO_UPGRADE_TEST_ORDERING_NODE_ID": ocp_phase_node_id,
            "IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID": cnv_phase_node_id,
        }

    # Default case: standard upgrade
    upgrade_class = "TestUpgrade"
    upgrade_source_suffix = "_production_source" if py_config.get("cnv_source") == "production" else ""
    test_name = f"test{upgrade_source_suffix}_{upgraded_product}_upgrade_process"
    file_name = f"{UPGRADE_PACKAGE_NAME}/test_upgrade.py"
    node_id = f"{file_name}::{upgrade_class}::{test_name}"
    return {
        "OCP_PHASE_NODE_ID": ocp_phase_node_id,
        "CNV_PHASE_NODE_ID": cnv_phase_node_id,
        "IUO_UPGRADE_TEST_ORDERING_NODE_ID": node_id,
        "IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID": node_id,
    }


def __getattr__(name: str) -> str | None:
    """Module-level __getattr__ for lazy access to config-dependent values."""
    if name in _LAZY_ATTRS:
        return _compute_upgrade_params()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
