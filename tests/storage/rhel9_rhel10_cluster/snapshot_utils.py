from __future__ import annotations

from typing import TYPE_CHECKING

from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.rhel9_rhel10_cluster.constants import (
    SNAPSHOT_TEST_DATA,
    SNAPSHOT_TEST_FILE,
)
from utilities.constants.timeouts import TIMEOUT_10MIN
from utilities.storage import run_command_on_vm_and_check_output
from utilities.virt import running_vm, set_vm_affinity

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTestsFromTemplate


def assert_vm_rhcos_version(
    vm: VirtualMachineForTestsFromTemplate, admin_client: DynamicClient, expected_os: str
) -> None:
    """Assert VM is running on expected RHCOS version.

    Args:
        vm: VirtualMachine under test
        admin_client: DynamicClient for KubeVirt operations
        expected_os: Expected OS string (e.g., "CoreOS 9" or "CoreOS 10")
    """
    node = vm.vmi.get_node(privileged_client=admin_client)
    os_image = node.instance.status.nodeInfo.osImage
    assert expected_os in os_image, f"VM {vm.name} expected on {expected_os}, but found {os_image}"


def verify_snapshot_restore_across_rhcos(
    admin_client: DynamicClient,
    vm: VirtualMachineForTestsFromTemplate,
    target_affinity: dict,
    target_rhcos_version: str,
) -> None:
    """Snapshot a stopped VM with test data, change affinity, restore, verify it runs on target RHCOS.

    VM is pre-configured with test data on source RHCOS and stopped (by fixture).
    Change affinity to target RHCOS BEFORE snapshot. Restore preserves the target affinity,
    so when started, VM runs on target RHCOS with original data intact.

    Args:
        admin_client: DynamicClient for KubeVirt operations
        vm: VirtualMachine under test (stopped, with test data written, by fixture)
        target_affinity: Target affinity dict to change to before snapshot
        target_rhcos_version: Expected RHCOS version after restore (e.g., "CoreOS 9" or "CoreOS 10")
    """
    test_file = SNAPSHOT_TEST_FILE
    test_content = SNAPSHOT_TEST_DATA

    # Change affinity to target RHCOS BEFORE snapshot so snapshot captures target affinity
    set_vm_affinity(vm=vm, affinity=target_affinity)

    with VirtualMachineSnapshot(
        name=f"snapshot-{vm.name}",
        namespace=vm.namespace,
        vm_name=vm.name,
        client=admin_client,
    ) as snapshot:
        snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)

        with VirtualMachineRestore(
            name=f"restore-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
            snapshot_name=snapshot.name,
            client=admin_client,
        ) as restore:
            restore.wait_restore_done(timeout=TIMEOUT_10MIN)

            # Start restored VM - it should run on target RHCOS node (affinity from snapshot)
            running_vm(vm=vm)

            # Verify VM is on target RHCOS node (affinity was preserved from snapshot)
            assert_vm_rhcos_version(vm=vm, admin_client=admin_client, expected_os=target_rhcos_version)

            # Verify data was preserved across restore and RHCOS version change
            run_command_on_vm_and_check_output(
                vm=vm,
                command=f"cat {test_file}",
                expected_result=test_content,
            )
