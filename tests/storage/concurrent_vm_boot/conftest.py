import gc
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype

from tests.storage.concurrent_vm_boot.constants import NUM_CONCURRENT_VMS
from tests.storage.concurrent_vm_boot.utils import VM_INSTANCE_TYPE, create_vm_with_disks
from utilities.constants.timeouts import TIMEOUT_30MIN
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def vms_with_four_disks(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """20 VMs each with 1 golden image boot volume (PVC clone) and 3 blank DVs, not yet started"""
    instance_type = VirtualMachineClusterInstancetype(
        name=VM_INSTANCE_TYPE, client=unprivileged_client, ensure_exists=True
    )

    vms = []
    try:
        failed_indices = []
        with ThreadPoolExecutor(max_workers=NUM_CONCURRENT_VMS) as executor:
            futures = {
                executor.submit(
                    create_vm_with_disks,
                    index=vm_index,
                    namespace_name=namespace.name,
                    client=unprivileged_client,
                    storage_class_name=storage_class_name_scope_module,
                    data_source=fedora_data_source_scope_module,
                    vm_instance_type=instance_type,
                ): vm_index
                for vm_index in range(NUM_CONCURRENT_VMS)
            }
            for future in as_completed(futures):
                vm_index = futures[future]
                try:
                    vms.append(future.result())
                except Exception as error:
                    LOGGER.error(f"Failed to create VM index {vm_index}: {error}")
                    failed_indices.append(vm_index)

        if failed_indices:
            pytest.fail(f"{len(failed_indices)}/{NUM_CONCURRENT_VMS} VMs failed to create: {failed_indices}")

        yield vms
    finally:
        cleanup_errors = []
        with ThreadPoolExecutor(max_workers=len(vms) or 1) as executor:
            futures = {executor.submit(vm.clean_up): vm for vm in vms}
            for future in as_completed(futures):
                vm = futures[future]
                try:
                    future.result()
                except Exception as error:
                    LOGGER.error(f"Failed to clean up VM {vm.name}: {error}")
                    cleanup_errors.append(vm.name)
        # Force garbage collection to prevent memory leaks due to paramiko/paramiko#2568
        gc.collect()
        if cleanup_errors:
            raise RuntimeError(f"Failed to clean up VMs: {cleanup_errors}")


@pytest.fixture(scope="module")
def started_vms_with_four_disks(vms_with_four_disks):
    """All 20 VMs started simultaneously"""
    failed_starts = []
    with ThreadPoolExecutor(max_workers=len(vms_with_four_disks)) as executor:
        futures = {executor.submit(vm.start, wait=False): vm for vm in vms_with_four_disks}
        for future in as_completed(futures):
            vm = futures[future]
            try:
                future.result()
            except Exception as error:
                LOGGER.error(f"Failed to start VM {vm.name}: {error}")
                failed_starts.append(vm.name)

    if failed_starts:
        pytest.fail(f"{len(failed_starts)}/{len(vms_with_four_disks)} VMs failed to start: {failed_starts}")

    yield vms_with_four_disks


@pytest.fixture(scope="module")
def running_vms_with_four_disks(started_vms_with_four_disks):
    """All 20 VMs in Running state"""
    failed = []
    with ThreadPoolExecutor(max_workers=len(started_vms_with_four_disks)) as executor:
        futures = {
            executor.submit(
                wait_for_running_vm,
                vm=vm,
                wait_until_running_timeout=TIMEOUT_30MIN,
                # Disk count verified via VMI API, SSH not needed
                check_ssh_connectivity=False,
            ): vm
            for vm in started_vms_with_four_disks
        }
        for future in as_completed(futures):
            vm = futures[future]
            try:
                future.result()
            except Exception as error:
                LOGGER.error(f"VM {vm.name} failed to reach Running state: {error}")
                failed.append(vm.name)

    if failed:
        pytest.fail(f"{len(failed)}/{len(started_vms_with_four_disks)} VMs failed to boot: {failed}")

    yield started_vms_with_four_disks
