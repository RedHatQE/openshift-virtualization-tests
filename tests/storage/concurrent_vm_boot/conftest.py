import logging
from gc import collect

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from tests.storage.concurrent_vm_boot.constants import NUM_CONCURRENT_VMS, REQUIRED_CLUSTER_MEMORY_GI
from tests.storage.concurrent_vm_boot.utils import (
    assert_cluster_memory,
    create_concurrent_vm,
    run_parallel,
    run_vms_parallel,
)
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL
from utilities.constants.timeouts import TIMEOUT_10MIN
from utilities.exceptions import ClusterSanityError
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cluster_memory_for_concurrent_vms(schedulable_nodes):
    """Assert the cluster has enough aggregate allocatable memory for the concurrent VM boot test.

    The budget is derived from the instance type (2 GiB guest RAM per u1.small VM) plus a
    1 GiB per-VM overhead margin for virt-launcher and the gap between allocatable and free
    memory. Storage capacity is not pre-checked: the storage class supports dynamic provisioning
    and PVC scheduling failures surface quickly during concurrent VM creation — add a storage
    preflight if false-negative timeouts become a problem.

    Args:
        schedulable_nodes: Schedulable worker nodes used to compute aggregate allocatable memory.

    Raises:
        ClusterSanityError: If aggregate allocatable memory is below the required threshold.
    """
    assert_cluster_memory(nodes=schedulable_nodes, required_gi=REQUIRED_CLUSTER_MEMORY_GI)


@pytest.fixture(scope="module")
def created_vms_with_five_disks(
    request,
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
    fedora_data_source_scope_module,
):
    """Create 20 VMs each with 1 golden image boot volume, 1 cloud-init disk, and 3 blank DVs.

    VMs are created concurrently and not yet started. All VMs are cleaned up in the finally block
    regardless of test outcome.

    Args:
        request: Pytest request for tracking test session failure state.
        unprivileged_client: Kubernetes client for resource operations.
        namespace: Test namespace for VM deployment.
        storage_class_name_scope_module: Storage class for boot and blank PVCs.
        fedora_data_source_scope_module: Fedora golden image DataSource for boot volumes.

    Yields:
        List of deployed VirtualMachineForTests instances, not yet started.

    Raises:
        ClusterSanityError: If any VMs fail to create or if cleanup fails after a successful run.
    """
    instance_type = VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client, ensure_exists=True)
    preference = VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA, client=unprivileged_client, ensure_exists=True)

    vms = []
    failed_labels: list[str] = []
    testsfailed_before = request.session.testsfailed
    try:
        vms, failed_labels = run_parallel(
            items=list(range(NUM_CONCURRENT_VMS)),
            func=lambda vm_index: create_concurrent_vm(
                index=vm_index,
                namespace_name=namespace.name,
                client=unprivileged_client,
                storage_class_name=storage_class_name_scope_module,
                data_source=fedora_data_source_scope_module,
                vm_instance_type=instance_type,
                vm_preference=preference,
                os_flavor=OS_FLAVOR_FEDORA,
            ),
            label="Failed to create VM index",
        )
        if failed_labels:
            raise ClusterSanityError(
                err_str=f"{len(failed_labels)}/{NUM_CONCURRENT_VMS} VMs failed to create: {failed_labels}"
            )

        yield vms
    finally:
        errors = run_vms_parallel(
            vms=vms,
            func=lambda vm: vm.clean_up(),
            label="Failed to clean up VM",
        )
        # Force GC to reclaim thread-local state and deferred object cleanup after concurrent workload.
        collect()
        if errors:
            cleanup_msg = f"Failed to clean up VMs: {errors}"
            if failed_labels or request.session.testsfailed > testsfailed_before:
                LOGGER.error(cleanup_msg)
            else:
                raise ClusterSanityError(err_str=cleanup_msg)


@pytest.fixture(scope="module")
def started_vms_with_five_disks(created_vms_with_five_disks):
    """Submit start requests for all VMs concurrently without waiting for boot.

    Args:
        created_vms_with_five_disks: Deployed VMs not yet started.

    Yields:
        Same VM list with start requests submitted.

    Raises:
        ClusterSanityError: If any VMs fail to accept the start request.
    """
    errors = run_vms_parallel(
        vms=created_vms_with_five_disks,
        func=lambda vm: vm.start(wait=False),
        label="Failed to start VM",
    )
    if errors:
        raise ClusterSanityError(
            err_str=f"{len(errors)}/{len(created_vms_with_five_disks)} VMs failed to start: {errors}"
        )
    yield created_vms_with_five_disks


@pytest.fixture(scope="module")
def running_vms_with_five_disks(started_vms_with_five_disks):
    """Wait for all VMs to reach Running state with SSH connectivity confirmed.

    Args:
        started_vms_with_five_disks: VMs with start requests submitted.

    Yields:
        Same VM list, all confirmed running with SSH connectivity.

    Raises:
        ClusterSanityError: If any VMs fail to reach Running state within the timeout.
    """
    errors = run_vms_parallel(
        vms=started_vms_with_five_disks,
        func=lambda vm: wait_for_running_vm(
            vm=vm,
            wait_until_running_timeout=TIMEOUT_10MIN,
            check_ssh_connectivity=True,
        ),
        label="VM failed to reach Running state",
    )
    if errors:
        raise ClusterSanityError(
            err_str=f"{len(errors)}/{len(started_vms_with_five_disks)} VMs failed to boot: {errors}"
        )
    yield started_vms_with_five_disks
