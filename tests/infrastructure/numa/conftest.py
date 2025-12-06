import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)

from utilities.constants import DATA_SOURCE_NAME
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm

CX1_CLUSTER_INSTANCETYPE_MEMORY_SIZES = [2, 4, 8, 16, 32, 64]  # provided cluster cx1 instancetype sizes (Gi)


@pytest.fixture(scope="module")
def preferred_cluster_cx1_instance_type(admin_client, hugepages_gib_max):
    instancetype_api = Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO
    smaller_memory_list = [memory for memory in CX1_CLUSTER_INSTANCETYPE_MEMORY_SIZES if memory < hugepages_gib_max]
    if not smaller_memory_list:
        pytest.fail(f"No CX1 size below {hugepages_gib_max}Gi")

    instance_type_selector = (
        f"{instancetype_api}/class=compute.exclusive,"
        f"{instancetype_api}/memory={max(smaller_memory_list)}Gi,"
        f"{instancetype_api}/hugepages=1Gi"
    )

    instances = list(VirtualMachineClusterInstancetype.get(client=admin_client, label_selector=instance_type_selector))
    if not instances:
        pytest.fail(f"No instancetype found for selector: {instance_type_selector}")

    return instances[0]


@pytest.fixture(scope="module")
def created_vm_cx1_instancetype(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_rhel_os_matrix__module__,
    storage_class_matrix__module__,
    preferred_cluster_cx1_instance_type,
):
    os_name = next(iter(instance_type_rhel_os_matrix__module__))
    data_source_name = instance_type_rhel_os_matrix__module__[os_name][DATA_SOURCE_NAME]

    with VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{data_source_name}-cx1-vm",
        namespace=namespace.name,
        vm_instance_type=preferred_cluster_cx1_instance_type,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                client=unprivileged_client,
                name=data_source_name,
                namespace=golden_images_namespace.name,
            ),
            storage_class=[*storage_class_matrix__module__][0],
        ),
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def migrated_numa_cx1_vm(
    created_vm_cx1_instancetype,
):
    migrate_vm_and_verify(vm=created_vm_cx1_instancetype, check_ssh_connectivity=True)
