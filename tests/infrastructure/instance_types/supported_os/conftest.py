import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import config as py_config

from tests.infrastructure.instance_types.supported_os.utils import golden_image_vm_with_instance_type
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.constants import (
    CONTAINER_DISK_IMAGE_PATH_STR,
    DATA_SOURCE_NAME,
    DATA_SOURCE_STR,
    OS_FLAVOR_WIN_CONTAINER_DISK,
    RHEL8_PREFERENCE,
    Images,
)
from utilities.storage import get_test_artifact_server_url
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
def windows_data_volume_template(
    unprivileged_client,
    namespace,
    windows_os_matrix__module__,
):
    os_matrix_key = [*windows_os_matrix__module__][0]
    os_params = windows_os_matrix__module__[os_matrix_key]
    secret = get_artifactory_secret(namespace=namespace.name)
    cert = get_artifactory_config_map(namespace=namespace.name)
    win_dv = DataVolume(
        client=unprivileged_client,
        name=f"{os_matrix_key}-dv",
        namespace=namespace.name,
        api_name="storage",
        source="registry",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        url=f"{get_test_artifact_server_url(schema='registry')}/{os_params[CONTAINER_DISK_IMAGE_PATH_STR]}",
        secret=secret,
        cert_configmap=cert.name,
    )
    win_dv.to_dict()
    yield win_dv
    cleanup_artifactory_secret_and_config_map(artifactory_secret=secret, artifactory_config_map=cert)


@pytest.fixture(scope="class")
def golden_image_windows_vm(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    windows_data_volume_template,
    windows_os_matrix__module__,
):
    os_name = [*windows_os_matrix__module__][0]
    return VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{os_name}-vm-with-instance-type-2",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name="u1.large"),
        vm_preference=VirtualMachineClusterPreference(
            client=unprivileged_client,
            name=windows_os_matrix__module__[os_name][DATA_SOURCE_STR].replace("win", "windows."),
        ),
        data_volume_template=windows_data_volume_template.res,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        disk_type=None,
        cpu_model=modern_cpu_for_migration,
    )
