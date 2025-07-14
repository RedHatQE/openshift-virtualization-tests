from ocp_resources.data_source import DataSource

from utilities.constants import DATA_SOURCE_NAME
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests


def golden_image_vm_with_instance_type(
    client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    storage_class_matrix,
    os_matrix,
):
    os_name = [*os_matrix][0]
    return VirtualMachineForTests(
        client=client,
        name=f"{os_name}-vm-with-instance-type",
        namespace=namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=os_matrix[os_name][DATA_SOURCE_NAME],
                namespace=golden_images_namespace.name,
            ),
            storage_class=[*storage_class_matrix][0],
        ),
        cpu_model=modern_cpu_for_migration,
    )
