from __future__ import annotations

from typing import TYPE_CHECKING

from utilities.constants import Images
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.storage import data_volume_template_dict_with_pvc_source
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.datavolume import DataVolume


def create_vm_from_clone_dv_template(
    vm_name: str,
    dv_name: str,
    namespace_name: str,
    source_dv: DataVolume,
    client: DynamicClient,
    volume_mode: str,
    storage_class: str,
    size: str | None = None,
) -> None:
    """Create a VM with a single cloned DataVolume template and verify it boots.

    Args:
        vm_name: Name for the VM.
        dv_name: Name for the cloned DataVolume.
        namespace_name: Target namespace.
        source_dv: Source DataVolume to clone from.
        client: Kubernetes client.
        volume_mode: Volume mode for the cloned DV.
        storage_class: Storage class for the cloned DV.
        size: Optional size override for the cloned DV.
    """
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        os_flavor=OS_FLAVOR_FEDORA,
        client=client,
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_dict_with_pvc_source(
            target_dv_name=dv_name,
            target_dv_namespace=namespace_name,
            source_dv=source_dv,
            volume_mode=volume_mode,
            size=size,
            storage_class=storage_class,
        ),
    ) as vm:
        running_vm(vm=vm)
