"""
Test for predictable DataVolume and PersistentVolumeClaim names when restoring a VM.

Jira: https://redhat.atlassian.net/browse/CNV-80304
"""

import pytest
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.storage.utils import vm_restore_with_prefix_policy
from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_10MIN
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

VOLUME_RESTORE_POLICY = "PrefixTargetName"
SOURCE_VM_NAME = "source-fedora-vm"
RESTORED_VM_NAME = "restored-fedora-vm"


@pytest.fixture()
def vm_for_predictable_names(
    request,
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
):
    """Create VM with DataVolume for predictable names testing."""
    params = getattr(request, "param", {})
    source_vm_name = params.get("source_vm_name", SOURCE_VM_NAME)

    with VirtualMachineForTests(
        name=source_vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=py_config["default_storage_class"],
        ),
        cloud_init_data=None,
    ) as vm:
        source_volume_name = vm.instance.spec.template.spec.volumes[0].name

        yield {
            "vm": vm,
            "source_vm_name": vm.name,
            "source_volume_name": source_volume_name,
            "params": params,
        }


@pytest.fixture()
def snapshot_for_predictable_names(
    vm_for_predictable_names,
    admin_client,
    namespace,
):
    """Create snapshot from VM for predictable names testing."""
    vm_data = vm_for_predictable_names
    source_vm_name = vm_data["source_vm_name"]
    snapshot_name = f"{source_vm_name}-snapshot"[:63]

    with VirtualMachineSnapshot(
        name=snapshot_name,
        namespace=namespace.name,
        vm_name=source_vm_name,
        client=admin_client,
    ) as snapshot:
        snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)

        yield {
            **vm_data,
            "snapshot": snapshot,
        }


@pytest.fixture()
def restore_data_for_predictable_names(
    snapshot_for_predictable_names,
    admin_client,
    namespace,
):
    """Create restore and fetch restored resources for predictable names testing."""
    snapshot_data = snapshot_for_predictable_names
    params = snapshot_data["params"]
    restored_vm_name = params.get("restored_vm_name", RESTORED_VM_NAME)
    source_vm_name = snapshot_data["source_vm_name"]
    source_volume_name = snapshot_data["source_volume_name"]
    snapshot = snapshot_data["snapshot"]

    with vm_restore_with_prefix_policy(
        name=f"{restored_vm_name}-restore",
        namespace=namespace.name,
        vm_name=restored_vm_name,
        snapshot_name=snapshot.name,
        client=admin_client,
        prefix_policy=VOLUME_RESTORE_POLICY,
    ) as restored_vm:
        restored_vm.wait_restore_done(timeout=TIMEOUT_10MIN)

        restore_status = restored_vm.instance.status
        assert restore_status.restores, f"No restores found in VirtualMachineRestore {restored_vm.name} status"

        restored_dv_name = restore_status.restores[0].dataVolumeName
        restored_pvc_name = restore_status.restores[0].persistentVolumeClaim

        assert restored_dv_name, f"No dataVolumeName in restore status for {restored_vm.name}"
        assert restored_pvc_name, f"No persistentVolumeClaim in restore status for {restored_vm.name}"

        actual_policy = restored_vm.instance.spec.get("volumeRestorePolicy")

        yield {
            "source_volume_name": source_volume_name,
            "source_vm_name": source_vm_name,
            "restored_vm_name": restored_vm_name,
            "restored_dv_name": restored_dv_name,
            "restored_pvc_name": restored_pvc_name,
            "volumeRestorePolicy": actual_policy,
        }

        if restored_vm.exists:
            restored_vm.delete(wait=True)


@pytest.mark.polarion("CNV-80304")
@pytest.mark.parametrize(
    "vm_for_predictable_names",
    [
        pytest.param(
            {"source_vm_name": "short-vm", "restored_vm_name": "restored-short"},
            id="short_names",
        ),
        pytest.param(
            {
                "source_vm_name": "very-long-source-vm-name-that-might-exceed-limits",
                "restored_vm_name": "very-long-restored-vm-name-that-might-exceed-limits",
            },
            id="long_names_truncated",
        ),
        pytest.param(
            {"source_vm_name": "vm-with-numbers-123", "restored_vm_name": "restored-456"},
            id="names_with_numbers",
        ),
    ],
    indirect=True,
)
def test_restored_dv_and_pvc_names_have_vm_prefix(restore_data_for_predictable_names):
    """
    Verify restored DataVolume and PVC names are prefixed with target VM name for various name combinations.

    Preconditions:
        - VM created and running from DataSource
        - Snapshot created from stopped VM
        - Restore created with PrefixTargetName policy
        - Test parametrized with different source and restored VM name combinations

    Steps:
        1. Extract original volume name from source VM spec
        2. Extract restored DataVolume name from restore status
        3. Extract restored PVC name from restore status
        4. Construct expected name as "{restored_vm_name}-{source_volume_name}" truncated to 63 chars
        5. Verify restored DV name matches expected pattern
        6. Verify restored PVC name matches expected pattern

    Expected:
        - Restored DataVolume name is "{restored_vm_name}-{source_volume_name}" truncated to 63 characters
        - Restored PVC name is "{restored_vm_name}-{source_volume_name}" truncated to 63 characters
        - Pattern holds for short names, long names, and names with numbers

    Markers:
        - polarion: CNV-80304b
    """
    source_volume_name = restore_data_for_predictable_names["source_volume_name"]
    restored_vm_name = restore_data_for_predictable_names["restored_vm_name"]
    restored_dv_name = restore_data_for_predictable_names["restored_dv_name"]
    restored_pvc_name = restore_data_for_predictable_names["restored_pvc_name"]
    volume_restore_policy = restore_data_for_predictable_names["volumeRestorePolicy"]

    expected_restored_name = f"{restored_vm_name}-{source_volume_name}"[:63]

    assert volume_restore_policy == VOLUME_RESTORE_POLICY, (
        f"volumeRestorePolicy is '{volume_restore_policy}', expected '{VOLUME_RESTORE_POLICY}'"
    )

    assert restored_dv_name == expected_restored_name, (
        f"Restored DV name is '{restored_dv_name}', expected '{expected_restored_name}'"
    )

    assert restored_pvc_name == expected_restored_name, (
        f"Restored PVC name is '{restored_pvc_name}', expected '{expected_restored_name}'"
    )
