import datetime
import logging
import time

import pytest
from ocp_resources.utils.resource_constants import ResourceConstants

from utilities.constants import FILE_NAME_FOR_BACKUP, TEXT_TO_TEST, TIMEOUT_3MIN, TIMEOUT_5MIN
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup, create_rhel_vm, is_storage_class_support_volume_mode
from utilities.storage import write_file
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def rhel_vm_with_dv_running(request, chaos_namespace, snapshot_storage_class_name_scope_module):
    # Get the volume_mode; if test function uses @pytest.mark.volume_mode, override the default
    marker = request.node.get_closest_marker(name="volume_mode")
    requested_mode = marker.args[0] if marker else request.param.get("volume_mode", "filesystem")

    # Normalize to KubeVirt allowed values
    if requested_mode.lower() == "block":
        volume_mode = "Block"
    else:
        volume_mode = "Filesystem"

    # Only check Block support
    if volume_mode == "Block" and not is_storage_class_support_volume_mode(
        snapshot_storage_class_name_scope_module, "Block"
    ):
        pytest.skip(f"Storage class {snapshot_storage_class_name_scope_module!r} doesn't support volume mode 'Block'")

    vm_name = request.param.get("vm_name")

    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=chaos_namespace.name,
        vm_name=vm_name,
        dv_name=f"dv-{vm_name}",
        volume_mode=volume_mode,
        wait_running=True,
        rhel_image=request.param.get("rhel_image"),
    ) as vm:
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
        backup.wait_for_status(status=ResourceConstants.Backup.Status.INPROGRESS, timeout=TIMEOUT_3MIN)
        time.sleep(5)
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
def drain_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm = rhel_vm_with_dv_running
    vm_node = vm.vmi.node
    with node_mgmt_console(node=vm_node, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=vm_node, status=False, timeout=TIMEOUT_5MIN)
        yield vm_node
    wait_for_node_schedulable_status(node=vm_node, status=True, timeout=TIMEOUT_5MIN)
