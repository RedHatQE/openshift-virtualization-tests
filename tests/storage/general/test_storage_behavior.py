"""
General storage behavior tests
"""

import logging

import pytest

from tests.storage.cdi_import.utils import get_importer_pod_node, wait_dv_and_get_importer, wait_for_pvc_recreate
from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from utilities import console
from utilities.constants import OS_FLAVOR_FEDORA, REGISTRY_STR, TIMEOUT_1MIN, TIMEOUT_12MIN, Images
from utilities.infra import get_node_selector_dict
from utilities.storage import (
    create_dummy_first_consumer_pod,
    create_dv,
    create_vm_from_dv,
    sc_volume_binding_mode_is_wffc,
)

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)

ALLOCATION_SIZE_BYTES = 42949672960  # 40GiB in bytes


@pytest.mark.sno
@pytest.mark.polarion("CNV-675")
def test_pvc_recreates_after_deletion(fedora_data_volume, namespace, storage_class_name_scope_function):
    """
    Test that a PVC is automatically recreated by CDI after manual deletion.

    Preconditions:
        - Fedora DataSource available
        - Storage class available
        - DataVolume created from Fedora DataSource
        - PVC bound and DataVolume import completed

    Steps:
        1. Record the PVC original creation timestamp
        2. Delete the PVC
        3. Wait for PVC to be recreated with a new timestamp
        4. Create a dummy first consumer pod if storage class uses WaitForFirstConsumer binding mode
        5. Wait for DataVolume to reach Succeeded status

    Expected:
        - PVC is recreated automatically
        - DataVolume status is "Succeeded"
    """
    pvc = fedora_data_volume.pvc
    pvc_original_timestamp = pvc.instance.metadata.creationTimestamp
    pvc.delete()
    wait_for_pvc_recreate(pvc=pvc, pvc_creation_timestamp=pvc_original_timestamp)
    if sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_function, client=namespace.client):
        create_dummy_first_consumer_pod(pvc=pvc)
    fedora_data_volume.wait_for_dv_success()


@pytest.mark.polarion("CNV-3065")
@pytest.mark.sno
def test_disk_falloc(fedora_vm_with_instance_type):
    """
    Test that attempting to allocate more space than available on a disk fails with the expected error.

    Preconditions:
        - VM with instance type and preference created and running with console access

    Steps:
        1. Connect to VM console
        2. Execute fallocate command to allocate a file larger than the available disk space
        3. Verify the error message

    Expected:
        - fallocate command fails with "No space left on device" error
    """
    with console.Console(vm=fedora_vm_with_instance_type) as vm_console:
        LOGGER.info(f"Attempting to allocate {ALLOCATION_SIZE_BYTES} bytes to trigger disk full error")
        vm_console.sendline(f"fallocate -l {ALLOCATION_SIZE_BYTES} test-file")
        vm_console.expect("No space left on device", timeout=TIMEOUT_1MIN)


@pytest.mark.polarion("CNV-3632")
def test_vm_from_dv_on_different_node(
    admin_client,
    unprivileged_client,
    schedulable_nodes,
    namespace,
    storage_class_matrix_rwx_matrix__function__,
):
    """
    Test that a VM created from a DataVolume runs on a different node than the import operation.

    Preconditions:
        - Storage class with RWX access mode (shared storage like Ceph or NFS)
        - Multiple schedulable nodes available

    Steps:
        1. Create DataVolume from Quay registry without waiting for completion
        2. Get the importer pod that handles the registry import
        3. Record the node where the importer pod is running
        4. Wait for DataVolume to complete successfully
        5. Create and start a VM from the DataVolume on a different node
        6. Verify the VM is running on a different node than the importer pod

    Expected:
        - VM runs successfully on a node different from the import operation node
    """
    storage_class_name = next(iter(storage_class_matrix_rwx_matrix__function__))
    with create_dv(
        dv_name=f"fedora-dv-different-node-{storage_class_name}",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name,
        client=admin_client,
    ) as dv:
        LOGGER.info(f"Getting importer pod for DataVolume {dv.name}")
        importer_pod = wait_dv_and_get_importer(dv=dv, admin_client=admin_client)
        importer_pod_node = get_importer_pod_node(importer_pod=importer_pod)
        LOGGER.info(f"Importer pod {importer_pod.name} is running on node {importer_pod_node}")

        nodes = [node for node in schedulable_nodes if node.name != importer_pod_node]
        assert nodes, f"No available nodes different from importer pod node {importer_pod_node}"

        dv.wait_for_dv_success(timeout=TIMEOUT_12MIN)

        with create_vm_from_dv(
            client=unprivileged_client,
            dv=dv,
            vm_name="fedora-vm-different-node",
            os_flavor=OS_FLAVOR_FEDORA,
            node_selector=get_node_selector_dict(node_selector=nodes[0].name),
            memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        ) as vm:
            assert vm.vmi.node.name != importer_pod_node, (
                f"VM is running on the same node as importer pod. Expected different nodes. "
                f"Importer pod node: {importer_pod_node}, VM node: {vm.vmi.node.name}"
            )
