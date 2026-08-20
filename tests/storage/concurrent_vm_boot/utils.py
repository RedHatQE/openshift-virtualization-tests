"""Utilities for concurrent VM boot tests."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.datavolume import DataVolume

from tests.storage.concurrent_vm_boot.constants import BLANK_DV_SIZE, NUM_BLANK_DISKS_PER_VM
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.storage import add_dv_to_vm, construct_datavolume_source_dict, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource
    from ocp_resources.node import Node
    from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype

LOGGER = logging.getLogger(__name__)


def run_parallel(
    items: list[Any],
    func: Callable[..., Any],
    label: str,
    item_name: Callable[[Any], str] = str,
) -> tuple[list[Any], list[str]]:
    """Run func concurrently for each item, collecting results and error labels.

    Args:
        items: Items to process.
        func: Callable accepting one item and returning a value.
        label: Log prefix used in failure messages.
        item_name: Function to produce a display name from an item for logging and error tracking.

    Returns:
        Tuple of (results, errors) where results are successful return values and
        errors are display names of items for which func raised an exception.
    """
    if not items:
        raise ValueError("run_parallel called with empty items list")
    results: list[Any] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(items)) as executor:
        futures = {executor.submit(func, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                name = item_name(item)
                LOGGER.error(f"{label} {name}: {error}")
                errors.append(name)
    return results, errors


def run_vms_parallel(
    vms: list[VirtualMachineForTests],
    func: Callable[[VirtualMachineForTests], Any],
    label: str,
) -> list[str]:
    """Run func concurrently for each VM and collect the names of any that fail.

    Args:
        vms: VMs to process.
        func: Callable accepting a single VM as its first positional argument.
        label: Log prefix used in failure messages (e.g. "Failed to start VM").

    Returns:
        Names of VMs for which func raised an exception.
    """
    if not vms:
        return []
    _, errors = run_parallel(
        items=vms,
        func=func,
        label=label,
        item_name=lambda vm: vm.name,
    )
    return errors


def assert_cluster_memory(nodes: list[Node], required_gi: int) -> None:
    """Assert the cluster has sufficient aggregate allocatable memory.

    Args:
        nodes: Schedulable cluster nodes.
        required_gi: Minimum required aggregate allocatable memory in GiB.

    Raises:
        RuntimeError: If aggregate allocatable memory across all nodes is below required_gi.
    """
    total_bytes = sum(parse_quantity(node.instance.status.allocatable.memory) for node in nodes)
    required_bytes = required_gi * (2**30)
    if total_bytes < required_bytes:
        raise RuntimeError(
            f"Insufficient cluster memory: {total_bytes / (2**30):.1f}Gi allocatable across "
            f"{len(nodes)} schedulable nodes, need ≥ {required_gi}Gi"
        )


def blank_dv_template(name: str, namespace: str, storage_class_name: str) -> dict[str, Any]:
    """Build a blank DataVolume template dict suitable for VM dataVolumeTemplates.

    Args:
        name: DataVolume name.
        namespace: Target namespace (stripped from the returned dict for template use).
        storage_class_name: Storage class for the blank PVC.

    Returns:
        Mutable DataVolume resource dict with namespace removed, ready for use in
        VM dataVolumeTemplates.
    """
    dv = DataVolume(
        name=name,
        namespace=namespace,
        source_dict=construct_datavolume_source_dict(source="blank"),
        size=BLANK_DV_SIZE,
        storage_class=storage_class_name,
        api_name="storage",
    )
    dv.to_dict()  # populates dv.res with the full resource dict
    dv.res["metadata"].pop("namespace", None)
    return dv.res


def create_concurrent_vm(
    index: int,
    namespace_name: str,
    client: DynamicClient,
    storage_class_name: str,
    data_source: DataSource,
    vm_instance_type: VirtualMachineClusterInstancetype,
) -> VirtualMachineForTests:
    """Create and deploy a VM with a golden image boot volume and blank data disks.

    Deploys the VM and patches NUM_BLANK_DISKS_PER_VM blank DataVolume templates into
    its spec. On failure, cleans up the partially created VM before re-raising.

    Args:
        index: VM index used in the name (e.g. ``concurrent-vm-0``).
        namespace_name: Namespace to deploy the VM into.
        client: Kubernetes client for resource operations.
        storage_class_name: Storage class for boot and blank PVCs.
        data_source: Fedora golden image DataSource for the boot volume.
        vm_instance_type: Cluster instance type to assign to the VM.

    Returns:
        Deployed VirtualMachineForTests with all disks attached.
    """
    vm_name = f"concurrent-vm-{index}"
    LOGGER.info(f"Creating VM {vm_name}")

    vm = VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        client=client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=vm_instance_type,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class_name,
        ),
    )

    try:
        vm.deploy(wait=True)
        for disk_index in range(NUM_BLANK_DISKS_PER_VM):
            add_dv_to_vm(
                vm=vm,
                template_dv=blank_dv_template(
                    name=f"{vm_name}-blank-{disk_index}",
                    namespace=namespace_name,
                    storage_class_name=storage_class_name,
                ),
            )
    except Exception as exc:
        LOGGER.error(f"Failed to set up VM {vm_name}, cleaning up: {exc}")
        try:
            vm.clean_up()
        except Exception as cleanup_error:
            LOGGER.error(f"Failed to clean up VM {vm_name}: {cleanup_error}")
        raise RuntimeError(f"VM {vm_name}: setup failed") from exc

    LOGGER.info(f"VM {vm_name} created with {NUM_BLANK_DISKS_PER_VM} blank disks attached")
    return vm
