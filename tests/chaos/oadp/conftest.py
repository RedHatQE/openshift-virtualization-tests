import datetime
import logging

import pytest
from ocp_resources.data_source import DataSource
from pytest_testconfig import py_config

from utilities.constants import (
    BACKUP_STORAGE_LOCATION,
    DATA_SOURCE_STR,
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    TIMEOUT_3MIN,
    TIMEOUT_10MIN,
)
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup
from utilities.storage import data_volume_template_with_source_ref_dict, write_file
from utilities.virt import VirtualMachineForTests, node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def rhel_vm_with_dv_running(
    admin_client, chaos_namespace, golden_images_namespace, snapshot_storage_class_name_scope_module
):
    """
    Create a RHEL VM with a DataVolume for the whole test class.
    """

    with VirtualMachineForTests(
        client=admin_client,
        name="vm-oadp-chaos",
        namespace=chaos_namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=py_config["latest_rhel_os_dict"][DATA_SOURCE_STR],
                namespace=golden_images_namespace.name,
                ensure_exists=True,
            ),
            storage_class=snapshot_storage_class_name_scope_module,
        ),
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
    # Ensure VM is running before starting a backup
    if not rhel_vm_with_dv_running.ready:
        rhel_vm_with_dv_running.start(wait=True)

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


@pytest.fixture()
def drained_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm_node = rhel_vm_with_dv_running.vmi.node
    with node_mgmt_console(node=vm_node, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=vm_node, status=False)
        yield vm_node


@pytest.fixture()
def cordoned_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm_node = rhel_vm_with_dv_running.vmi.node
    with node_mgmt_console(node=vm_node, node_mgmt="cordon"):
        wait_for_node_schedulable_status(node=vm_node, status=False)
        yield vm_node
