"""
General storage behavior tests
"""

import logging

import pytest

from tests.storage.cdi_import.utils import wait_for_pvc_recreate
from utilities import console
from utilities.constants import TIMEOUT_1MIN
from utilities.storage import create_dummy_first_consumer_pod, sc_volume_binding_mode_is_wffc

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
