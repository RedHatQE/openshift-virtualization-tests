import logging
from contextlib import contextmanager

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.data_source import DataSource
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.constants import OS_FLAVOR_FEDORA, U1_SMALL
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@contextmanager
def create_vm_from_data_source_with_instance_type(
    vm_name: str,
    namespace: str,
    client: DynamicClient,
    data_source: DataSource,
    storage_class: str,
) -> VirtualMachine:
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace,
        os_flavor=OS_FLAVOR_FEDORA,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class,
        ),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False, wait_for_interfaces=False)  # TODO make True
        yield vm


@pytest.fixture()
def source_vm_for_storage_class_migration(admin_client, namespace, golden_images_fedora_data_source, request):
    with create_vm_from_data_source_with_instance_type(
        vm_name="vm-for-test",
        namespace=namespace.name,
        client=admin_client,  # TODO replace to unpriv before merge
        data_source=golden_images_fedora_data_source,
        storage_class=request.param["source_storage_class"],
    ) as vm:
        yield vm


@pytest.fixture()
def target_storage_class(request):
    return request.param["target_storage_class"]
