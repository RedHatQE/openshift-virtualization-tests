from tests.storage.utils import assert_clone_type_on_pvcs
from utilities.constants import Images
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.storage import (
    add_dv_to_vm,
    check_disk_count_in_vm,
    data_volume_template_dict_with_pvc_source,
)
from utilities.virt import VirtualMachineForTests, running_vm


def create_vm_from_clone_dv_template(
    vm_name,
    dv_name,
    namespace_name,
    source_dv,
    client,
    volume_mode,
    storage_class,
    size=None,
):
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


def create_vm_with_multi_clone_disks(
    vm_name,
    dv_name,
    namespace_name,
    source_dv,
    client,
    storage_class,
    num_disks,
    expected_clone_type,
):
    """Create a VM with multiple cloned disks and verify clone strategy.

    Args:
        vm_name: Name for the VM.
        dv_name: Base name for the cloned DataVolumes.
        namespace_name: Target namespace.
        source_dv: Source DataVolume to clone from.
        client: Kubernetes client.
        storage_class: Storage class for the cloned DVs.
        num_disks: Total number of disks to attach.
        expected_clone_type: Expected CDI clone strategy annotation value.

    Raises:
        AssertionError: If disk count or clone type annotations don't match.
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
            storage_class=storage_class,
        ),
    ) as vm:
        pvc_names = [dv_name]
        for idx in range(1, num_disks):
            disk_name = f"{dv_name}-{idx}"
            pvc_names.append(disk_name)
            add_dv_to_vm(
                vm=vm,
                template_dv=data_volume_template_dict_with_pvc_source(
                    target_dv_name=disk_name,
                    target_dv_namespace=namespace_name,
                    source_dv=source_dv,
                    storage_class=storage_class,
                ),
            )
        running_vm(vm=vm)
        check_disk_count_in_vm(vm=vm)
        assert_clone_type_on_pvcs(
            pvc_names=pvc_names,
            namespace=namespace_name,
            client=client,
            expected_clone_type=expected_clone_type,
        )
