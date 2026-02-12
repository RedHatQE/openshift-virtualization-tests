import datetime
import logging

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from timeout_sampler import TimeoutSampler

from tests.chaos.utils import create_pod_deleting_thread, pod_deleting_process_recover
from utilities.constants import (
    BACKUP_STORAGE_LOCATION,
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_10MIN,
    Images,
)
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup, create_rhel_vm
from utilities.storage import write_file
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def rhel_vm_with_dv_running(admin_client, chaos_namespace, snapshot_storage_class_name_scope_module):
    """
    Create a RHEL VM with a DataVolume.
    """
    vm_name = "rhel-vm"

    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=chaos_namespace.name,
        vm_name=vm_name,
        dv_name=f"dv-{vm_name}",
        client=admin_client,
        wait_running=True,
        rhel_image=Images.Rhel.RHEL9_3_IMG,
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


@pytest.fixture()
def drain_vm_source_node(admin_client, rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm_node = rhel_vm_with_dv_running.vmi.node
    with node_mgmt_console(admin_client=admin_client, node=vm_node, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=vm_node, status=False)
        yield vm_node


@pytest.fixture()
def pod_deleting_thread_during_oadp_operations(request, admin_client):
    pod_prefix = request.param["pod_prefix"]
    namespace_name = request.param["namespace_name"]

    thread, stop_event = create_pod_deleting_thread(
        client=admin_client,
        pod_prefix=pod_prefix,
        namespace_name=namespace_name,
        ratio=request.param["ratio"],
        interval=request.param["interval"],
        max_duration=request.param["max_duration"],
    )

    yield {
        "thread": thread,
        "stop_event": stop_event,
        "namespace_name": namespace_name,
        "pod_prefix": pod_prefix,
    }

    stop_event.set()
    if thread.is_alive():
        thread.join(timeout=TIMEOUT_1MIN)


@pytest.fixture()
def backup_with_pod_deletion_orchestration(
    oadp_backup_in_progress,
    pod_deleting_thread_during_oadp_operations,
):
    backup = oadp_backup_in_progress
    thread = pod_deleting_thread_during_oadp_operations["thread"]
    stop_event = pod_deleting_thread_during_oadp_operations["stop_event"]

    thread.start()

    terminal_statuses = {
        backup.Backup.Status.COMPLETED,
        backup.Backup.Status.FAILED,
        backup.Backup.Status.PARTIALLYFAILED,
        backup.Backup.Status.FAILEDVALIDATION,
    }

    final_status = None

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: backup.instance.status.phase,
        ):
            if sample in terminal_statuses:
                final_status = sample
                break

        yield final_status

    finally:
        stop_event.set()
        if thread.is_alive():
            thread.join(timeout=TIMEOUT_1MIN)

        # Verify recovery if applicable
        try:
            pod_deleting_process_recover(
                resources=[Deployment, DaemonSet],
                namespace=pod_deleting_thread_during_oadp_operations["namespace_name"],
                pod_prefix=pod_deleting_thread_during_oadp_operations["pod_prefix"],
            )
        except Exception:
            LOGGER.error(
                f"Recovery failed for prefix "
                f"{pod_deleting_thread_during_oadp_operations['pod_prefix']} "
                f"in namespace {pod_deleting_thread_during_oadp_operations['namespace_name']}"
            )
            raise
