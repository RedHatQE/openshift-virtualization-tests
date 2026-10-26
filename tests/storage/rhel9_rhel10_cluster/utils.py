from __future__ import annotations

from typing import TYPE_CHECKING

from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.constants import TEST_FILE_NAME
from tests.storage.rhel9_rhel10_cluster.constants import SNAPSHOT_TEST_DATA, SNAPSHOT_TEST_FILE
from tests.storage.utils import mount_hotplug_volume
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.storage import run_command_on_vm_and_check_output
from utilities.virt import running_vm, set_vm_affinity

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

HOTPLUG_DISK_SERIAL: str = "hotplugmig"
HOTPLUG_MOUNT_POINT: str = "/mnt/hotplug"
HOTPLUG_TEST_FILE: str = f"{HOTPLUG_MOUNT_POINT}/{TEST_FILE_NAME}"


def assert_vm_rhcos_version(vm: VirtualMachineForTests, admin_client: DynamicClient, expected_os: str) -> None:
    """Assert that the VM is running on the expected RHCOS version.

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
    vm: VirtualMachineForTests,
    target_affinity: dict,
    target_rhcos_version: str,
) -> None:
    """Snapshot a stopped VM, restore to target RHCOS, verify data and node placement.

    VM is pre-configured with test data on source RHCOS and stopped (by fixture).
    Change affinity to target RHCOS, create snapshot (captures target affinity),
    restore snapshot, and verify VM runs on target RHCOS with original data intact.

    Args:
        admin_client: DynamicClient for KubeVirt operations
        vm: VirtualMachine under test (stopped, with test data written, by fixture)
        target_affinity: Affinity dict to apply before creating the snapshot
        target_rhcos_version: Expected RHCOS version after restore (e.g., "CoreOS 9" or "CoreOS 10")
    """
    # Change affinity to target RHCOS before snapshot, so the snapshot captures target affinity
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

            # Start restored VM — should run on target RHCOS node (affinity from snapshot)
            running_vm(vm=vm)

            # Verify VM is on target RHCOS node (affinity was preserved from snapshot)
            assert_vm_rhcos_version(vm=vm, admin_client=admin_client, expected_os=target_rhcos_version)

            # Verify original test data is intact after restore
            run_command_on_vm_and_check_output(
                vm=vm,
                command=f"cat {SNAPSHOT_TEST_FILE}",
                expected_result=SNAPSHOT_TEST_DATA,
            )


def prepare_hotplug_disk(vm: VirtualMachineForTests, serial: str) -> None:
    """Format and mount the hotplugged blank disk in the guest.

    Args:
        vm: VM that contains the hotplugged disk.
        serial: Serial number used to select the blank disk.
    """
    device = (
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=["bash", "-c", f"lsblk -rno NAME,SERIAL | grep {serial}"],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            exceptions_dict=None,
        )[0]
        .strip()
        .split()[0]
    )
    mount_hotplug_volume(vm=vm, device=f"/dev/{device}", mount_path=HOTPLUG_MOUNT_POINT)
