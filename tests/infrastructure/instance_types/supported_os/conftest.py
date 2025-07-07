import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import config as py_config

from utilities.constants import CONTAINER_DISK_IMAGE_PATH_STR, OS_FLAVOR_WINDOWS, TIMEOUT_15MIN, Images
from utilities.storage import (
    create_dv,
    create_or_update_data_source,
    data_volume_template_with_source_ref_dict,
    get_test_artifact_server_url,
)
from utilities.virt import VirtualMachineForTests


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
    golden_images_namespace,
    modern_cpu_for_migration,
    golden_image_windows_data_source,
    windows_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = [*windows_os_matrix__module__][0]
    return VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{os_name}-vm-with-instance-type",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(name="u1.large"),
        vm_preference=VirtualMachineClusterPreference(name="windows.10"),
        # TODO add inference after default values labels are added to the image
        # vm_instance_type_infer=True,
        # vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_windows_data_source,
            storage_class=[*storage_class_matrix__module__][0],
        ),
        os_flavor=OS_FLAVOR_WINDOWS,
        disk_type=None,
        cpu_model=modern_cpu_for_migration,
    )


@pytest.fixture(scope="session")
def artifact_docker_server_url():
    return get_test_artifact_server_url(schema="registry")


@pytest.fixture(scope="class")
def skip_if_rhel8(instance_type_rhel_os_matrix__module__):
    current_rhel_name = [*instance_type_rhel_os_matrix__module__][0]
    if current_rhel_name == "rhel-8":
        pytest.xfail("EFI is not enabled by default before RHEL9")
