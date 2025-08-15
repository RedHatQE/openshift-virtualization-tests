import datetime
import logging

import pytest

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5MIN
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import (
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    VeleroBackup,
    create_rhel_vm,
    is_storage_class_support_volume_mode,
)
from utilities.storage import write_file
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def rhel_vm_with_dv_running(
    request,
    chaos_namespace,
    snapshot_storage_class_name_scope_module,
):
    volume_mode = request.param.get("volume_mode")
    if not is_storage_class_support_volume_mode(
        storage_class_name=snapshot_storage_class_name_scope_module,
        requested_volume_mode=volume_mode,
    ):
        pytest.skip(
            f"Storage class: {snapshot_storage_class_name_scope_module} doesn't support volume mode: {volume_mode}"
        )

    vm_name = request.param.get("vm_name")

    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=chaos_namespace.name,
        vm_name=vm_name,
        dv_name=f"dv-{vm_name}",
        wait_running=True,
        volume_mode=volume_mode,
        rhel_image=request.param.get("rhel_image"),
    ) as vm:
        vm.vmi.wait_until_running(timeout=TIMEOUT_3MIN)

        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
        )
        yield vm


@pytest.fixture()
def oadp_backup_in_progress(chaos_namespace, rhel_vm_with_dv_running):
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"backup-{timestamp}"

    with VeleroBackup(
        name=backup_name,
        included_namespaces=[chaos_namespace.name],
        snapshot_move_data=True,
        storage_location="dpa-1",
        wait_complete=False,
    ) as backup:
        LOGGER.info(f"Created backup: {backup_name}. Waiting for it to enter 'InProgress'...")
        backup.wait_for_status(status="InProgress", timeout=TIMEOUT_3MIN)
        yield backup


@pytest.fixture()
def rebooted_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress, workers_utility_pods):
    vm = rhel_vm_with_dv_running
    vm_node = vm.vmi.node

    LOGGER.info(f"Rebooting node {vm_node.name}")
    ExecCommandOnPod(utility_pods=workers_utility_pods, node=vm_node).exec(command="shutdown -r now", ignore_rc=True)
    wait_for_node_status(node=vm_node, status=False, wait_timeout=TIMEOUT_5MIN)

    LOGGER.info(f"Waiting for node {vm_node.name} to come back online")
    wait_for_node_status(node=vm_node, status=True, wait_timeout=TIMEOUT_5MIN)
    yield vm_node


@pytest.fixture()
def cordon_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm = rhel_vm_with_dv_running
    vm_node = vm.vmi.node
    with node_mgmt_console(node=vm_node, node_mgmt="cordon"):
        wait_for_node_schedulable_status(node=vm_node, status=False, timeout=TIMEOUT_5MIN)
