import gc
import logging

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype

from tests.storage.concurrent_vm_boot.constants import NUM_CONCURRENT_VMS, VM_INSTANCE_TYPE
from tests.storage.concurrent_vm_boot.utils import (
    assert_cluster_memory,
    create_concurrent_vm,
    run_parallel,
    run_vms_parallel,
)
from utilities.constants.timeouts import TIMEOUT_30MIN
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cluster_memory_for_concurrent_vms(schedulable_nodes):
    """Assert the cluster has enough aggregate allocatable memory for the concurrent VM boot test."""
    assert_cluster_memory(nodes=schedulable_nodes, required_gi=NUM_CONCURRENT_VMS)


@pytest.fixture(scope="module")
def vms_with_five_disks(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
    fedora_data_source_scope_module,
    cluster_memory_for_concurrent_vms,
):
    """VMs each with 1 golden image boot volume, 1 cloud-init disk, and 3 blank DVs, not yet started."""

    instance_type = VirtualMachineClusterInstancetype(
        name=VM_INSTANCE_TYPE, client=unprivileged_client, ensure_exists=True
    )

    vms = []
    failed_indices: list[int] = []
    primary_failure = False
    try:
        vms, failed_indices = run_parallel(
            items=list(range(NUM_CONCURRENT_VMS)),
            func=lambda vm_index: create_concurrent_vm(
                index=vm_index,
                namespace_name=namespace.name,
                client=unprivileged_client,
                storage_class_name=storage_class_name_scope_module,
                data_source=fedora_data_source_scope_module,
                vm_instance_type=instance_type,
            ),
            label="Failed to create VM index",
        )
        if failed_indices:
            pytest.fail(f"{len(failed_indices)}/{NUM_CONCURRENT_VMS} VMs failed to create: {failed_indices}")

        try:
            yield vms
        except Exception:
            primary_failure = True
            raise
    finally:
        errors = run_vms_parallel(
            vms=vms,
            func=lambda vm: vm.clean_up(),
            label="Failed to clean up VM",
        )
        # Force GC to reclaim thread-local state and deferred object cleanup after concurrent workload.
        gc.collect()
        if errors:
            cleanup_msg = f"Failed to clean up VMs: {errors}"
            if failed_indices or primary_failure:
                LOGGER.error(cleanup_msg)
            else:
                pytest.fail(cleanup_msg)


@pytest.fixture(scope="module")
def started_vms_with_five_disks(vms_with_five_disks):
    """All VMs started simultaneously."""
    errors = run_vms_parallel(
        vms=vms_with_five_disks,
        func=lambda vm: vm.start(wait=False),
        label="Failed to start VM",
    )
    if errors:
        pytest.fail(f"{len(errors)}/{len(vms_with_five_disks)} VMs failed to start: {errors}")
    yield vms_with_five_disks


@pytest.fixture(scope="module")
def running_vms_with_five_disks(started_vms_with_five_disks):
    """All VMs in Running state."""
    # 30-minute timeout provides ~10× headroom over the ~3 min observed on tested clusters,
    # accommodating slower storage provisioning on constrained environments.
    errors = run_vms_parallel(
        vms=started_vms_with_five_disks,
        func=lambda vm: wait_for_running_vm(
            vm=vm,
            wait_until_running_timeout=TIMEOUT_30MIN,
            check_ssh_connectivity=False,
        ),
        label="VM failed to reach Running state",
    )
    if errors:
        pytest.fail(f"{len(errors)}/{len(started_vms_with_five_disks)} VMs failed to boot: {errors}")
    yield started_vms_with_five_disks
