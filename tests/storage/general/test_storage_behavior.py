"""
General storage behavior tests
"""

import logging

import pytest

from tests.storage.cdi_import.utils import wait_for_pvc_recreate
from utilities import console
from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_1MIN, Images
from utilities.infra import get_node_selector_dict
from utilities.storage import create_dummy_first_consumer_pod, create_vm_from_dv, sc_volume_binding_mode_is_wffc

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)


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
    if sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_function):
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
    allocation_size_bytes = 42949672960  # 40GiB in bytes, assuming DV is about 30Gi
    with console.Console(vm=fedora_vm_with_instance_type) as vm_console:
        LOGGER.info(f"Attempting to allocate {allocation_size_bytes} bytes to trigger disk full error")
        vm_console.sendline(f"fallocate -l {allocation_size_bytes} test-file")
        vm_console.expect("No space left on device", timeout=TIMEOUT_1MIN)


@pytest.mark.polarion("CNV-3632")
def test_vm_from_dv_on_different_node(
    unprivileged_client,
    schedulable_nodes,
    fedora_dv_rwx_with_importer_node,
):
    """
    Test that a VM created from a DataVolume runs on a different node than the import operation.

    Preconditions:
        - Storage class with RWX access mode (shared storage like Ceph or NFS)
        - Multiple schedulable nodes available
        - DataVolume imported from Quay registry

    Steps:
        1. Get nodes excluding the importer pod node
        2. Create and start a VM from the DataVolume on a different node
        3. Verify the VM is running on a different node than the importer pod

    Expected:
        - VM runs successfully on a node different from the import operation node
    """
    dv, importer_pod_node = fedora_dv_rwx_with_importer_node

    nodes = [node for node in schedulable_nodes if node.name != importer_pod_node]
    assert nodes, f"No available nodes different from importer pod node {importer_pod_node}"

    with create_vm_from_dv(
        dv=dv,
        vm_name="fedora-vm-different-node",
        os_flavor=OS_FLAVOR_FEDORA,
        node_selector=get_node_selector_dict(node_selector=nodes[0].name),
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
    ) as vm:
        vmi_node_name = vm.vmi.node.name
        assert vmi_node_name != importer_pod_node, (
            f"VM is running on the same node as importer pod. Expected different nodes. "
            f"Importer pod node: {importer_pod_node}, VM node: {vmi_node_name}"
        )
