"""
Storage general tests fixtures
"""

import logging

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from tests.storage.cdi_import.utils import get_importer_pod_node, wait_dv_and_get_importer
from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from utilities.constants import OS_FLAVOR_FEDORA, REGISTRY_STR, TIMEOUT_5MIN, TIMEOUT_12MIN, U1_SMALL, Images
from utilities.storage import create_dv, data_volume_template_with_source_ref_dict, get_dv_size_from_datasource
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


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
        name="fedora-vm",
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


@pytest.fixture()
def fedora_dv_rwx_with_importer_node(
    admin_client,
    unprivileged_client,
    namespace,
    storage_class_matrix_rwx_matrix__function__,
):
    """
    Provides a DataVolume imported from Quay registry with importer pod node information.

    Returns:
        Tuple of (DataVolume, importer_pod_node_name) where the DataVolume is ready
        and importer_pod_node_name is the node where the import operation ran.
    """
    storage_class_name = next(iter(storage_class_matrix_rwx_matrix__function__))
    with create_dv(
        dv_name=f"fedora-dv-different-node-{storage_class_name}",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name,
        client=unprivileged_client,
    ) as dv:
        LOGGER.info(f"Getting importer pod for DataVolume {dv.name}")
        importer_pod = wait_dv_and_get_importer(dv=dv, admin_client=admin_client)
        importer_pod_node = get_importer_pod_node(importer_pod=importer_pod)
        LOGGER.info(f"Importer pod {importer_pod.name} is running on node {importer_pod_node}")

        dv.wait_for_dv_success(timeout=TIMEOUT_12MIN)

        yield dv, importer_pod_node
