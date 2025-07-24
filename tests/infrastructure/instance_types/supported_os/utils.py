from kubernetes.dynamic import DynamicClient
from ocp_resources.data_source import DataSource

from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests


def golden_image_vm_with_instance_type(
    client: DynamicClient,
    namespace_name: str,
    golden_images_namespace_name: str,
    modern_cpu_for_migration: str | None,
    storage_class_name: str,
    data_source_name: str,
) -> VirtualMachineForTests:
    return VirtualMachineForTests(
        client=client,
        name=f"{data_source_name}-vm-with-instance-type",
        namespace=namespace_name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=data_source_name,
                namespace=golden_images_namespace_name,
            ),
            storage_class=storage_class_name,
        ),
        cpu_model=modern_cpu_for_migration,
    )
