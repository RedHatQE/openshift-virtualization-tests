from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from sys import exception as current_exception
from time import monotonic
from typing import TYPE_CHECKING

import pytest
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.snapshots.constants import ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS, NUM_BLANK_DISKS
from tests.storage.utils import VMWithSeveralBlankDisks
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.timeouts import TIMEOUT_10MIN
from utilities.storage import check_disk_count_in_vm, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from typing import Any

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource
    from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
    from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

LOGGER = logging.getLogger(__name__)


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


def raise_cleanup_failures(message: str, cleanup_errors: list[Exception]) -> None:
    """Raise cleanup errors without replacing an in-flight setup or test failure.

    Args:
        message: ExceptionGroup message when cleanup errors are raised.
        cleanup_errors: Exceptions collected while cleaning resources.

    Raises:
        ExceptionGroup: Cleanup failures, including any exception already being handled.
    """
    if not cleanup_errors:
        return
    primary = current_exception()
    grouped_errors = [primary, *cleanup_errors] if isinstance(primary, Exception) else cleanup_errors
    cleanup_group = ExceptionGroup(message, grouped_errors)
    if primary is None:
        raise cleanup_group
    raise cleanup_group from primary


def run_parallel(
    items: list[Any],
    func: Callable[..., Any],
    label: str,
    item_name: Callable[[Any], str] = str,
) -> tuple[list[Any], list[Exception]]:
    """Run func concurrently for each item, collecting results and exceptions.

    Args:
        items: Items to process. An empty list returns empty results and errors.
        func: Callable accepting one item and returning a value.
        label: Log prefix used in failure messages.
        item_name: Function to produce a display name from an item for logging.

    Returns:
        Tuple of (results, errors) where results are successful return values and
        errors are exceptions raised by func.
    """
    if not items:
        return [], []
    results: list[Any] = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=len(items)) as executor:
        futures = {executor.submit(func, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                LOGGER.error(f"{label} {item_name(item)}: {error}")
                errors.append(error)
    return results, errors


def remaining_timeout(deadline: float, operation: str) -> float:
    """Return seconds left before a monotonic deadline.

    Args:
        deadline: Monotonic timestamp when the budget expires.
        operation: Description used in the timeout error.

    Returns:
        Remaining seconds until the deadline.

    Raises:
        TimeoutError: If the deadline has already passed.
    """
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError(f"{operation} exceeded the 5-minute budget")
    return remaining


def wait_restore_within_deadline(restore: VirtualMachineRestore, deadline: float) -> None:
    """Wait for restore complete and restoreInProgress=None within one deadline.

    Args:
        restore: Deployed VirtualMachineRestore to wait on.
        deadline: Monotonic timestamp when the restore budget expires.

    Raises:
        TimeoutError: If no time remains before a wait starts.
        ResourceNotFoundError: If the target VM does not exist.
    """
    restore.wait_complete(timeout=remaining_timeout(deadline=deadline, operation=f"Restore {restore.name} complete"))
    vm = VirtualMachine(client=restore.client, namespace=restore.namespace, name=restore.vm_name)
    if not vm.exists:
        raise ResourceNotFoundError(f"VirtualMachine: {vm.name} not found")
    vm.wait_for_status_none(
        status="restoreInProgress",
        timeout=remaining_timeout(deadline=deadline, operation=f"Restore {restore.name} restoreInProgress"),
    )


def restore_vm_within_deadline(restore: VirtualMachineRestore, deadline: float) -> VirtualMachineRestore:
    """Deploy a restore and wait for it to finish within the given deadline.

    Args:
        restore: VirtualMachineRestore to deploy and wait on.
        deadline: Monotonic timestamp when the restore budget expires.

    Returns:
        The same restore after complete and restoreInProgress=None.
    """
    LOGGER.info(f"Deploying restore {restore.name}")
    restore.deploy()
    LOGGER.info(f"Waiting for restore {restore.name} to complete")
    wait_restore_within_deadline(restore=restore, deadline=deadline)
    return restore


def create_vm_with_4_disks(
    vm_name: str,
    namespace_name: str,
    client: DynamicClient,
    storage_class_name: str,
    data_source: DataSource,
    vm_instance_type: VirtualMachineClusterInstancetype,
    vm_preference: VirtualMachineClusterPreference,
) -> VirtualMachineForTests:
    """Deploy a Fedora VM with 1 boot disk from DataSource and 3 blank DVs.

    All disks are included in the VM spec at creation time (single API call).
    The VM is deployed but not waited on for Running; callers start or wait separately.
    If deploy fails, the VM is cleaned up before re-raising.
    Cleanup failures are chained onto the original setup exception.

    Args:
        vm_name: Name for the VM.
        namespace_name: Namespace to deploy the VM into.
        client: Kubernetes client for resource operations.
        storage_class_name: Storage class for boot and blank PVCs.
        data_source: Fedora golden image DataSource for the boot volume.
        vm_instance_type: Pre-resolved instance type for the VM.
        vm_preference: Pre-resolved preference for the VM.

    Returns:
        Deployed VirtualMachineForTests with 4 disk devices, not yet confirmed Running.
    """
    vm = VMWithSeveralBlankDisks(
        name=vm_name,
        namespace=namespace_name,
        client=client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=vm_instance_type,
        vm_preference=vm_preference,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class_name,
        ),
        blank_disk_storage_class_name=storage_class_name,
        num_blank_disks=NUM_BLANK_DISKS,
    )
    try:
        LOGGER.info(f"Deploying VM {vm_name} with {NUM_BLANK_DISKS} blank disks")
        vm.deploy(wait=True)
    except Exception as error:
        LOGGER.error(f"Failed to deploy VM {vm_name}, cleaning up: {error}")
        try:
            vm.clean_up()
        except Exception as cleanup_error:
            LOGGER.error(f"Failed to clean up VM {vm_name}: {cleanup_error}")
            raise error from cleanup_error
        raise
    return vm


def assert_restored_vm_disk_count(vm: VirtualMachineForTests) -> None:
    """Start a restored VM and verify guest disk count matches the VM spec.

    Restore completion is already enforced by the restore fixture. Starting the VM
    and checking disks is outside the 5-minute restore budget.

    Args:
        vm: Restored VirtualMachineForTests to start and inspect.
    """
    LOGGER.info(f"Starting restored VM {vm.name} to verify disk count")
    running_vm(vm=vm)
    check_disk_count_in_vm(vm=vm)


def assert_restored_vms_disk_counts(vms: list[VirtualMachineForTests]) -> None:
    """Start restored VMs in parallel and verify guest disk count matches each VM spec.

    Args:
        vms: Restored VirtualMachineForTests objects to start and inspect.
    """
    _, disk_errors = run_parallel(
        items=vms,
        func=assert_restored_vm_disk_count,
        label="Failed to verify restored VM disks",
        item_name=lambda vm: vm.name,
    )
    assert not disk_errors, "Restored VMs failed disk verification: " + ", ".join(str(error) for error in disk_errors)
