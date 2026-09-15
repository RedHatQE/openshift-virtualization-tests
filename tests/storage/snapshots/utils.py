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
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from typing import Any

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource

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
    total = len(items)
    results: list[Any] = []
    errors: list[Exception] = []
    LOGGER.info(f"Starting parallel operations for {total} item(s)")
    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = {executor.submit(func, item): item for item in items}
        for completed_count, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            try:
                results.append(future.result())
                LOGGER.info(f"Completed {item_name(item)} ({completed_count}/{total})")
            except Exception as error:  # Broad catch required: func is caller-supplied, any exception type is valid
                LOGGER.error(f"{label} {item_name(item)}: {error} ({completed_count}/{total})")
                errors.append(error)
    return results, errors


def restore_vm_within_deadline(restore: VirtualMachineRestore, deadline: float) -> VirtualMachineRestore:
    """Deploy restore and wait for completion within deadline."""
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Restore deadline already exceeded")

    LOGGER.info(f"Deploying restore {restore.name} ({remaining:.0f}s budget)")
    restore.deploy()
    restore.wait_complete(timeout=remaining)

    vm = VirtualMachine(client=restore.client, namespace=restore.namespace, name=restore.vm_name)
    if not vm.exists:
        raise ResourceNotFoundError(f"VM {restore.vm_name} not found")
    vm.wait_for_status_none(status="restoreInProgress", timeout=deadline - monotonic())
    return restore


def create_vm_with_4_disks(
    vm_name: str,
    namespace_name: str,
    client: DynamicClient,
    storage_class_name: str,
    data_source: DataSource,
) -> VirtualMachineForTests:
    """Deploy a Fedora VM with 1 boot disk from DataSource and 3 blank DVs.

    All disks are included in the VM spec at creation time (single API call).
    The VM is deployed but not waited on for Running; callers start or wait separately.
    Instance type and preference are inferred for the test cluster's architecture.
    If deploy fails, the VM is cleaned up before re-raising with error chaining.

    Args:
        vm_name: Name for the VM.
        namespace_name: Namespace to deploy the VM into.
        client: Kubernetes client for resource operations.
        storage_class_name: Storage class for boot and blank PVCs.
        data_source: Fedora golden image DataSource for the boot volume.

    Returns:
        Deployed VirtualMachineForTests with 4 disk devices, not yet confirmed Running.
    """
    vm = VMWithSeveralBlankDisks(
        name=vm_name,
        namespace=namespace_name,
        client=client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
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
        LOGGER.info(f"VM {vm_name} deployed successfully")
    except Exception as deploy_error:
        LOGGER.error(f"Failed to deploy VM {vm_name}: {deploy_error}")
        try:
            vm.clean_up()
        except Exception as cleanup_error:
            LOGGER.error(f"Failed to clean up VM {vm_name}: {cleanup_error}")
            raise RuntimeError(f"Failed to clean up VM {vm_name}") from cleanup_error
        raise
    return vm
