import pytest

from tests.infrastructure.instance_types.supported_os.utils import golden_image_vm_with_instance_type
from utilities.constants import DATA_SOURCE_NAME


@pytest.fixture(scope="class")
def xfail_if_rhel8(instance_type_rhel_os_matrix__module__):
    current_rhel_name = [*instance_type_rhel_os_matrix__module__][0]
    if current_rhel_name == "rhel-8":
        pytest.xfail("EFI is not enabled by default before RHEL9")


@pytest.fixture(scope="module")
def golden_image_rhel_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_rhel_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_rhel_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_rhel_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )
