"""
Storage general tests fixtures
"""

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_5MIN, U1_SMALL
from utilities.storage import create_dv, data_volume_template_with_source_ref_dict, get_dv_size_from_datasource
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture()
def fedora_data_volume(namespace, fedora_data_source_scope_module, storage_class_name_scope_function):
    """
    Provides a DataVolume created from Fedora DataSource.

    The DataVolume is created and waits for success before yielding.
    """
    with create_dv(
        dv_name=f"fedora-dv-{storage_class_name_scope_function}",
        namespace=namespace.name,
        storage_class=storage_class_name_scope_function,
        size=get_dv_size_from_datasource(fedora_data_source_scope_module),
        client=namespace.client,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_5MIN)
        yield dv


@pytest.fixture()
def fedora_vm_with_instance_type(
    namespace,
    unprivileged_client,
    fedora_data_source_scope_module,
    storage_class_name_scope_function,
):
    """
    Provides a running Fedora VM with instance type and preference.

    The VM is created with U1_SMALL instance type and Fedora preference,
    using a DataVolume template from the provided data source.
    """
    with VirtualMachineForTests(
        name=f"vm-{storage_class_name_scope_function}",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA, client=unprivileged_client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=storage_class_name_scope_function,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm
