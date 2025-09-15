from contextlib import contextmanager

import pytest
from ocp_resources.virtual_machine import VirtualMachine

from tests.virt.utils import get_data_volume_template_dict_with_default_storage_class
from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, fedora_vm_body

default_run_strategy = VirtualMachine.RunStrategy.MANUAL


@contextmanager
def container_disk_vm(namespace, unprivileged_client, data_source=None):
    """lifecycle_vm is used to call this fixture and data_volume_vm; data_source is not needed in this use cases"""
    name = "fedora-vm-lifecycle"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=default_run_strategy,
    ) as vm:
        yield vm


@contextmanager
def data_volume_vm(unprivileged_client, namespace, data_source):
    with VirtualMachineForTests(
        name="rhel-vm-lifecycle",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
        run_strategy=default_run_strategy,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(data_source=data_source),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def lifecycle_vm(
    cluster_cpu_model_scope_module,
    unprivileged_client,
    namespace,
    vm_volumes_matrix__class__,
    golden_image_data_source_for_test_scope_module,
):
    """Wrapper fixture to generate the desired VM
    vm_volumes_matrix returns a string.
    globals() is used to call the actual contextmanager with that name
    request should be True to start vm and wait for interfaces, else False
    """
    with globals()[vm_volumes_matrix__class__](
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_for_test_scope_module,
    ) as vm:
        yield vm
