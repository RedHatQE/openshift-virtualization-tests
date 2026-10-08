import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.snapshots.constants import ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS
from utilities.constants.cluster import RHCOS9_WORKER_LABEL
from utilities.constants.timeouts import TIMEOUT_10MIN
from utilities.storage import run_command_on_vm_and_check_output, write_file_via_ssh
from utilities.virt import running_vm, set_vm_affinity


def expected_output_after_restore(snapshot_number):
    """
    Returns a string representing the list of files that should exist in the VM (sorted)
    after a restore snapshot was performed

    Args:
        snapshot_number (int): The snapshot number that was restored

    Returns:
        string: the list of files that should exist on the VM after restore operation was performed
    """
    files = []
    for idx in range(snapshot_number - 1):
        files.append(f"before-snap-{idx + 1}.txt")
        files.append(f"after-snap-{idx + 1}.txt")
    files.append(f"before-snap-{snapshot_number}.txt ")
    files.sort()
    return " ".join(files)


def fail_to_create_snapshot_no_permissions(snapshot_name, namespace, vm_name, client):
    with pytest.raises(
        ApiException,
        match=ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS,
    ):
        with VirtualMachineSnapshot(
            name=snapshot_name,
            namespace=namespace,
            vm_name=vm_name,
            client=client,
        ):
            return


def start_windows_vm_after_restore(vm_restore, windows_vm):
    vm_restore.wait_restore_done(timeout=TIMEOUT_10MIN)
    running_vm(vm=windows_vm)


def snapshot_restore_across_rhcos(admin_client, vm, expect_rhcos9_before, target_affinity):
    """Snapshot a VM, change affinity to target RHCOS version, restore, and verify node placement and data integrity.

    Args:
        admin_client: DynamicClient for KubeVirt operations
        vm: VirtualMachine under test
        expect_rhcos9_before: True if VM should be on RHCOS9 before snapshot, False for RHCOS10
        target_affinity: Target affinity dict for the opposite RHCOS version
    """
    node_labels = vm.vmi.get_node(privileged_client=admin_client).labels
    assert (RHCOS9_WORKER_LABEL in node_labels) == expect_rhcos9_before, (
        f"VM {vm.name} pre-snapshot node label mismatch"
    )

    # Write test data before snapshot
    test_file = "/tmp/snapshot-test.txt"
    test_content = "snapshot-restore-test-data"
    running_vm(vm=vm)
    write_file_via_ssh(vm=vm, filename=test_file, content=test_content)

    if vm.ready:
        vm.stop(wait=True)

    with VirtualMachineSnapshot(
        name=f"snapshot-{vm.name}",
        namespace=vm.namespace,
        vm_name=vm.name,
        client=admin_client,
    ) as snapshot:
        snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)
        set_vm_affinity(vm=vm, affinity=target_affinity)
        with VirtualMachineRestore(
            name=f"restore-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
            snapshot_name=snapshot.name,
            client=admin_client,
        ) as restore:
            restore.wait_restore_done(timeout=TIMEOUT_10MIN)
            running_vm(vm=vm)
            node_labels = vm.vmi.get_node(privileged_client=admin_client).labels
            assert (RHCOS9_WORKER_LABEL in node_labels) != expect_rhcos9_before, (
                f"VM {vm.name} post-restore node label mismatch"
            )

            # Verify data integrity with retry (SSH needs time to stabilize after restore)
            run_command_on_vm_and_check_output(
                vm=vm,
                command=f"cat {test_file}",
                expected_result=test_content,
            )
