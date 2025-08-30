import datetime
import logging

import pytest

from utilities.constants import BACKUP_STORAGE_LOCATION, FILE_NAME_FOR_BACKUP, TEXT_TO_TEST, TIMEOUT_3MIN, TIMEOUT_10MIN
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup, create_rhel_vm
from utilities.storage import write_file

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def rhel_vm_with_dv_running(request, admin_client, chaos_namespace, snapshot_storage_class_name_scope_module):
    """
    Create a RHEL VM with a DataVolume.
    """
    vm_name = request.param["vm_name"]

    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=chaos_namespace.name,
        vm_name=vm_name,
        dv_name=f"dv-{vm_name}",
        client=admin_client,
        wait_running=True,
        rhel_image=request.param["rhel_image"],
    ) as vm:
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
        )
        yield vm


@pytest.fixture()
def oadp_backup_in_progress(admin_client, chaos_namespace, rhel_vm_with_dv_running):
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"backup-{timestamp}"

    with VeleroBackup(
        name=backup_name,
        included_namespaces=[chaos_namespace.name],
        client=admin_client,
        snapshot_move_data=True,
        storage_location=BACKUP_STORAGE_LOCATION,
        wait_complete=False,
    ) as backup:
        backup.wait_for_status(status=backup.Backup.Status.INPROGRESS, timeout=TIMEOUT_3MIN)
        yield backup


@pytest.fixture()
def rebooted_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress, workers_utility_pods):
    vm_node = rhel_vm_with_dv_running.vmi.node

    LOGGER.info(f"Rebooting node {vm_node.name}")
    ExecCommandOnPod(utility_pods=workers_utility_pods, node=vm_node).exec(command="shutdown -r now", ignore_rc=True)
    wait_for_node_status(node=vm_node, status=False, wait_timeout=TIMEOUT_10MIN)

    LOGGER.info(f"Waiting for node {vm_node.name} to come back online")
    wait_for_node_status(node=vm_node, status=True, wait_timeout=TIMEOUT_10MIN)
    return
