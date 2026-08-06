"""Utilities for concurrent VM boot tests."""

import logging
from typing import TYPE_CHECKING, Any

from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype

from tests.storage.concurrent_vm_boot.constants import BLANK_DV_SIZE, NUM_BLANK_DISKS_PER_VM
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.storage import add_dv_to_vm, construct_datavolume_source_dict, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

LOGGER = logging.getLogger(__name__)
# u1.micro (1Gi RAM) without preference to fit 20 VMs on small clusters;
# preference is omitted because fedora preference enforces 2Gi minimum.
VM_INSTANCE_TYPE = "u1.micro"


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
    dv.res["metadata"].pop("namespace", None)
    return dv.res


def create_vm_with_disks(
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
        index: VM index used in the name (e.g. concurrent-vm-0).
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
