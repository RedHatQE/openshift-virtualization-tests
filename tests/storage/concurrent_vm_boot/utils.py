"""Utilities for concurrent VM boot tests."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from kubernetes.utils.quantity import parse_quantity
from ocp_resources.datavolume import DataVolume

from tests.storage.concurrent_vm_boot.constants import BLANK_DV_SIZE, NUM_BLANK_DISKS_PER_VM
from utilities.exceptions import ClusterSanityError
from utilities.storage import construct_datavolume_source_dict, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource
    from ocp_resources.node import Node
    from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
    from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

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

    Checks allocatable memory (node capacity minus system-reserved), not free/available memory
    (allocatable minus currently requested by running pods). Callers should include an overhead
    margin in ``required_gi`` to account for the gap between allocatable and truly free memory.

    Args:
        nodes: Schedulable cluster nodes.
        required_gi: Minimum required aggregate allocatable memory in GiB, including overhead margin.

    Raises:
        ClusterSanityError: If aggregate allocatable memory across all nodes is below required_gi.
    """
    total_bytes = sum(parse_quantity(node.instance.status.allocatable.memory) for node in nodes)
    required_bytes = required_gi * (2**30)
    if total_bytes < required_bytes:
        raise ClusterSanityError(
            err_str=(
                f"Insufficient cluster memory: {total_bytes / (2**30):.1f}Gi allocatable across "
                f"{len(nodes)} schedulable nodes, need ≥ {required_gi}Gi"
            )
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
    dv.to_dict()
    del dv.res["metadata"]["namespace"]
    return dv.res


class VMWithSeveralBlankDisks(VirtualMachineForTests):
    """VM that injects blank data disks at creation time to avoid post-creation PATCH calls."""

    def __init__(self, blank_disk_storage_class_name: str, num_blank_disks: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.blank_disk_storage_class_name = blank_disk_storage_class_name
        self.num_blank_disks = num_blank_disks

    def to_dict(self) -> None:
        """Build the VM resource dict and add blank disk entries to it.

        Note:
            Do not call more than once. Each call appends the blank disks to the resource dict,
            so a second call will result in duplicate disks.
        """
        super().to_dict()
        template_spec = self.res["spec"]["template"]["spec"]
        disks = template_spec["domain"]["devices"]["disks"]
        volumes = template_spec["volumes"]
        dv_templates = self.res["spec"]["dataVolumeTemplates"]

        for disk_index in range(self.num_blank_disks):
            dv_name = f"{self.name}-blank-{disk_index}"
            template = blank_dv_template(
                name=dv_name,
                namespace=self.namespace,
                storage_class_name=self.blank_disk_storage_class_name,
            )
            dv_templates.append(template)
            disks.append({"disk": {"bus": "virtio"}, "name": dv_name})
            volumes.append({"name": dv_name, "dataVolume": {"name": dv_name}})


def create_concurrent_vm(
    index: int,
    namespace_name: str,
    client: DynamicClient,
    storage_class_name: str,
    data_source: DataSource,
    vm_instance_type: VirtualMachineClusterInstancetype,
    vm_preference: VirtualMachineClusterPreference,
    os_flavor: str,
) -> VirtualMachineForTests:
    """Create and deploy a VM with a golden image boot volume and blank data disks.

    All disks are included in the VM spec at creation time (single API call).
    On failure, cleans up the partially created VM before re-raising.

    Args:
        index: VM index used in the name (e.g. ``concurrent-vm-0``).
        namespace_name: Namespace to deploy the VM into.
        client: Kubernetes client for resource operations.
        storage_class_name: Storage class for boot and blank PVCs.
        data_source: Golden image DataSource for the boot volume.
        vm_instance_type: Cluster instance type to assign to the VM.
        vm_preference: Cluster preference to assign to the VM.
        os_flavor: OS flavor string used for SSH login parameters and cloud-init.

    Returns:
        Deployed VirtualMachineForTests with all disks attached.
    """
    vm_name = f"concurrent-vm-{index}"
    LOGGER.info(f"Creating VM {vm_name}")

    vm = VMWithSeveralBlankDisks(
        name=vm_name,
        namespace=namespace_name,
        client=client,
        os_flavor=os_flavor,
        vm_instance_type=vm_instance_type,
        vm_preference=vm_preference,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class_name,
            name=f"{vm_name}-boot",
        ),
        blank_disk_storage_class_name=storage_class_name,
        num_blank_disks=NUM_BLANK_DISKS_PER_VM,
    )

    try:
        vm.deploy(wait=True)
    except Exception as exc:
        LOGGER.error(f"Failed to set up VM {vm_name}, cleaning up: {exc}")
        try:
            vm.clean_up()
        except Exception as cleanup_error:
            LOGGER.error(f"Failed to clean up VM {vm_name}: {cleanup_error}")
        raise ClusterSanityError(err_str=f"VM {vm_name}: setup failed: {exc}") from exc

    LOGGER.info(f"VM {vm_name} created with {NUM_BLANK_DISKS_PER_VM} blank disks attached")
    return vm
