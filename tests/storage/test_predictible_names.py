"""
Test for predictable DataVolume and PersistentVolumeClaim names when restoring a VM.

Jira: https://redhat.atlassian.net/browse/CNV-80304
"""

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.storage.utils import vm_restore_with_prefix_policy
from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_10MIN
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

VOLUME_RESTORE_POLICY = "PrefixTargetName"
SOURCE_VM_NAME = "source-fedora-vm"
RESTORED_VM_NAME = "restored-fedora-vm"


@pytest.fixture()
def vm_snapshot_restore_dicts_scope_function(
    request,
    unprivileged_client,
    admin_client,
    namespace,
    fedora_data_source_scope_module,
):
    """Create VM, snapshot, and restore resources on cluster to verify actual restored names."""
    params = getattr(request, "param", {})
    source_vm_name = params.get("source_vm_name", SOURCE_VM_NAME)
    restored_vm_name = params.get("restored_vm_name", RESTORED_VM_NAME)

    with VirtualMachineForTests(
        name=source_vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=py_config["default_storage_class"],
        ),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        source_dv_name = vm.instance.spec.dataVolumeTemplates[0].metadata.name

        vm.stop(wait=True)

        with VirtualMachineSnapshot(
            name=f"{source_vm_name}-snapshot",
            namespace=namespace.name,
            vm_name=source_vm_name,
            client=admin_client,
        ) as snapshot:
            snapshot.wait_ready_to_use(timeout=TIMEOUT_10MIN)

            with vm_restore_with_prefix_policy(
                name=f"{restored_vm_name}-restore",
                namespace=namespace.name,
                vm_name=restored_vm_name,
                snapshot_name=snapshot.name,
                client=admin_client,
                prefix_policy=VOLUME_RESTORE_POLICY,
                dry_run=False,
            ) as restore:
                restore.wait_restore_done(timeout=TIMEOUT_10MIN)

                restored_dvs = list(
                    DataVolume.get(
                        dyn_client=admin_client,
                        namespace=namespace.name,
                        label_selector=f"restore.kubevirt.io/source-vm-name={source_vm_name}",
                    )
                )
                restored_pvcs = list(
                    PersistentVolumeClaim.get(
                        dyn_client=admin_client,
                        namespace=namespace.name,
                        label_selector=f"restore.kubevirt.io/source-vm-name={source_vm_name}",
                    )
                )

                assert restored_dvs, (
                    f"No DataVolumes found with label restore.kubevirt.io/source-vm-name={source_vm_name}"
                )
                assert restored_pvcs, f"No PVCs found with label restore.kubevirt.io/source-vm-name={source_vm_name}"

                restored_dv_name = restored_dvs[0].name
                restored_pvc_name = restored_pvcs[0].name

                yield {
                    "source_dv_name": source_dv_name,
                    "source_pvc_name": source_dv_name,
                    "source_vm_name": vm.name,
                    "restored_vm_name": restored_vm_name,
                    "restored_dv_name": restored_dv_name,
                    "restored_pvc_name": restored_pvc_name,
                    "volumeRestorePolicy": restore.instance.spec.volumeRestorePolicy,
                }


class TestPredictableNamesOnRestore:
    """
    Tests for predictable DV and PVC names when restoring VMs with volumeRestorePolicy: PrefixTargetName.

    Preconditions:
        - Fedora DataSource available in golden images namespace
        - Default storage class configured
    """

    @pytest.mark.polarion("CNV-80304")
    @pytest.mark.usefixtures("vm_snapshot_restore_dicts_scope_function")
    def test_restored_dv_and_pvc_names_have_vm_prefix_default_names(self, vm_snapshot_restore_dicts_scope_function):
        """
        Verify restored DataVolume and PVC names are prefixed with target VM name.

        Preconditions:
            - VM created and running from DataSource
            - Snapshot created from stopped VM
            - Restore created with PrefixTargetName policy

        Steps:
            1. Extract original DataVolume name from source VM
            2. Extract original PVC name from source VM
            3. Extract restored DataVolume name from cluster
            4. Extract restored PVC name from cluster
            5. Verify restored DV name follows pattern "{restored_vm_name}-{source_dv_name}"
            6. Verify restored PVC name follows pattern "{restored_vm_name}-{source_pvc_name}"

        Expected:
            - Restored DataVolume name is "{restored_vm_name}-{source_dv_name}" truncated to 63 characters
            - Restored PVC name is "{restored_vm_name}-{source_pvc_name}" truncated to 63 characters

        Markers:
            - polarion: CNV-80304
        """
        source_dv_name = vm_snapshot_restore_dicts_scope_function["source_dv_name"]
        source_pvc_name = vm_snapshot_restore_dicts_scope_function["source_pvc_name"]
        restored_vm_name = vm_snapshot_restore_dicts_scope_function["restored_vm_name"]
        restored_dv_name = vm_snapshot_restore_dicts_scope_function["restored_dv_name"]
        restored_pvc_name = vm_snapshot_restore_dicts_scope_function["restored_pvc_name"]
        volume_restore_policy = vm_snapshot_restore_dicts_scope_function["volumeRestorePolicy"]

        expected_restored_dv_name = f"{restored_vm_name}-{source_dv_name}"[:63]
        expected_restored_pvc_name = f"{restored_vm_name}-{source_pvc_name}"[:63]

        assert volume_restore_policy == VOLUME_RESTORE_POLICY, (
            f"volumeRestorePolicy is '{volume_restore_policy}', expected '{VOLUME_RESTORE_POLICY}'"
        )

        assert restored_dv_name == expected_restored_dv_name, (
            f"Restored DV name is '{restored_dv_name}', expected '{expected_restored_dv_name}'"
        )

        assert restored_pvc_name == expected_restored_pvc_name, (
            f"Restored PVC name is '{restored_pvc_name}', expected '{expected_restored_pvc_name}'"
        )

    @pytest.mark.polarion("CNV-80304b")
    @pytest.mark.parametrize(
        "vm_snapshot_restore_dicts_scope_function",
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
    def test_restored_dv_and_pvc_names_have_vm_prefix_parametrized(self, vm_snapshot_restore_dicts_scope_function):
        """
        Verify restored DataVolume and PVC names are prefixed with target VM name for various name combinations.

        Preconditions:
            - VM created and running from DataSource
            - Snapshot created from stopped VM
            - Restore created with PrefixTargetName policy
            - Test parametrized with different source and restored VM name combinations

        Steps:
            1. Extract original DataVolume name from source VM
            2. Extract original PVC name from source VM
            3. Extract restored DataVolume name from cluster
            4. Extract restored PVC name from cluster
            5. Construct expected DV name as "{restored_vm_name}-{source_dv_name}" truncated to 63 chars
            6. Construct expected PVC name as "{restored_vm_name}-{source_pvc_name}" truncated to 63 chars
            7. Verify restored DV name matches expected pattern
            8. Verify restored PVC name matches expected pattern

        Expected:
            - Restored DataVolume name is "{restored_vm_name}-{source_dv_name}" truncated to 63 characters
            - Restored PVC name is "{restored_vm_name}-{source_pvc_name}" truncated to 63 characters
            - Pattern holds for short names, long names, and names with numbers

        Markers:
            - polarion: CNV-80304b
        """
        source_dv_name = vm_snapshot_restore_dicts_scope_function["source_dv_name"]
        source_pvc_name = vm_snapshot_restore_dicts_scope_function["source_pvc_name"]
        restored_vm_name = vm_snapshot_restore_dicts_scope_function["restored_vm_name"]
        restored_dv_name = vm_snapshot_restore_dicts_scope_function["restored_dv_name"]
        restored_pvc_name = vm_snapshot_restore_dicts_scope_function["restored_pvc_name"]
        volume_restore_policy = vm_snapshot_restore_dicts_scope_function["volumeRestorePolicy"]

        expected_restored_dv_name = f"{restored_vm_name}-{source_dv_name}"[:63]
        expected_restored_pvc_name = f"{restored_vm_name}-{source_pvc_name}"[:63]

        assert volume_restore_policy == VOLUME_RESTORE_POLICY, (
            f"volumeRestorePolicy is '{volume_restore_policy}', expected '{VOLUME_RESTORE_POLICY}'"
        )

        assert restored_dv_name == expected_restored_dv_name, (
            f"Restored DV name is '{restored_dv_name}', expected '{expected_restored_dv_name}'"
        )

        assert restored_pvc_name == expected_restored_pvc_name, (
            f"Restored PVC name is '{restored_pvc_name}', expected '{expected_restored_pvc_name}'"
        )
