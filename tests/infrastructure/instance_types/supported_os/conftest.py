import pytest
from pytest_testconfig import config as py_config

from tests.infrastructure.instance_types.supported_os.utils import golden_image_vm_with_instance_type
from utilities.constants import (
    CONTAINER_DISK_IMAGE_PATH_STR,
    DATA_SOURCE_NAME,
    RHEL8_PREFERENCE,
    TIMEOUT_15MIN,
    Images,
)
from utilities.storage import (
    create_dv,
    create_or_update_data_source,
    data_volume_template_with_source_ref_dict,
    get_test_artifact_server_url,
)
from utilities.virt import VirtualMachineForTests


@pytest.fixture(scope="class")
def xfail_if_rhel8(instance_type_rhel_os_matrix__module__):
    if [*instance_type_rhel_os_matrix__module__][0] == RHEL8_PREFERENCE:
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


@pytest.fixture(scope="module")
def golden_image_centos_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_centos_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_centos_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_centos_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )


@pytest.fixture(scope="module")
def golden_image_fedora_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_fedora_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_fedora_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_fedora_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )


@pytest.fixture(scope="module")
def golden_image_windows_data_source(
    admin_client,
    golden_images_namespace,
    windows_os_matrix__module__,
    artifact_docker_server_url,
):
    os_matrix_key = [*windows_os_matrix__module__][0]
    os_params = windows_os_matrix__module__[os_matrix_key]
    with create_dv(
        dv_name=os_matrix_key,
        namespace=golden_images_namespace.name,
        source="registry",
        url=f"{artifact_docker_server_url}/{os_params[CONTAINER_DISK_IMAGE_PATH_STR]}",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=py_config["default_storage_class"],
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_15MIN)
        yield from create_or_update_data_source(admin_client=admin_client, dv=dv)


@pytest.fixture(scope="class")
def golden_image_windows_vm(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    golden_image_windows_data_source,
    windows_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = [*windows_os_matrix__module__][0]
    return VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{os_name}-vm-with-instance-type-2",
        namespace=namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_windows_data_source,
            storage_class=[*storage_class_matrix__module__][0],
        ),
        os_flavor="win-container-disk",
        disk_type=None,
        cpu_model=modern_cpu_for_migration,
    )


@pytest.fixture(scope="session")
def artifact_docker_server_url():
    return get_test_artifact_server_url(schema="registry")
