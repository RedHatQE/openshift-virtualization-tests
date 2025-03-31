import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from utilities.constants import DATA_SOURCE_NAME
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

COMMON_INSTANCETYPE_SELECTOR = f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor=redhat.com"


@pytest.fixture()
def cluster_instance_type_for_test_scope_function(common_instance_type_param_dict):
    return VirtualMachineClusterInstancetype(**common_instance_type_param_dict)


@pytest.fixture(scope="class")
def vm_cluster_preference_for_test(common_vm_preference_param_dict):
    return VirtualMachineClusterPreference(**common_vm_preference_param_dict)


@pytest.fixture(scope="session")
def base_vm_cluster_preferences():
    return list(
        VirtualMachineClusterPreference.get(
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


@pytest.fixture(scope="session")
def base_vm_cluster_instancetypes():
    return list(
        VirtualMachineClusterInstancetype.get(
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


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
