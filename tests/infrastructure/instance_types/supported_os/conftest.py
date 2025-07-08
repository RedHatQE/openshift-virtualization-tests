import pytest
from ocp_resources.data_source import DataSource

from utilities.constants import DATA_SOURCE_NAME
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests


@pytest.fixture(scope="class")
def skip_if_rhel8(instance_type_rhel_os_matrix__module__):
    current_rhel_name = [*instance_type_rhel_os_matrix__module__][0]
    if current_rhel_name == "rhel-8":
        pytest.xfail("EFI is not enabled by default before RHEL9")


@pytest.fixture(scope="module")
def golden_image_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_rhel_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = [*instance_type_rhel_os_matrix__module__][0]
    return VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{os_name}-vm-with-instance-type",
        namespace=namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=instance_type_rhel_os_matrix__module__[os_name][DATA_SOURCE_NAME],
                namespace=golden_images_namespace.name,
            ),
            storage_class=[*storage_class_matrix__module__][0],
        ),
        cpu_model=modern_cpu_for_migration,
    )
