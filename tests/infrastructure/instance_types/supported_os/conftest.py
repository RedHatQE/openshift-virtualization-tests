import pytest

from tests.infrastructure.instance_types.supported_os.utils import golden_image_vm_with_instance_type


@pytest.fixture(scope="class")
def xfail_if_rhel8(instance_type_rhel_os_matrix__module__):
    if [*instance_type_rhel_os_matrix__module__][0] == "rhel-8":
        pytest.xfail("EFI is not enabled by default before RHEL9")


@pytest.fixture(scope="class")
def xfail_if_centos(instance_type_centos_fedora_os_matrix__module__):
    if [*instance_type_centos_fedora_os_matrix__module__][0] in ["centos-stream9", "centos-stream10"]:
        pytest.xfail("EFI is not enabled by default on CentOs")


@pytest.fixture(scope="module")
def golden_image_rhel_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_rhel_os_matrix__module__,
    storage_class_matrix__module__,
):
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace=namespace,
        golden_images_namespace=golden_images_namespace,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_matrix=storage_class_matrix__module__,
        os_matrix=instance_type_rhel_os_matrix__module__,
    )


@pytest.fixture(scope="module")
def golden_image_centos_fedora_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_centos_fedora_os_matrix__module__,
    storage_class_matrix__module__,
):
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace=namespace,
        golden_images_namespace=golden_images_namespace,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_matrix=storage_class_matrix__module__,
        os_matrix=instance_type_centos_fedora_os_matrix__module__,
    )
