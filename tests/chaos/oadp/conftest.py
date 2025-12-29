import datetime
import logging

import pytest
from timeout_sampler import TimeoutSampler

from tests.chaos.utils import create_pod_deleting_process, terminate_process
from utilities.constants import (
    BACKUP_STORAGE_LOCATION,
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    Images,
)
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup, VeleroRestore, create_rhel_vm
from utilities.storage import write_file
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

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


@pytest.fixture()
def drain_vm_source_node(rhel_vm_with_dv_running, oadp_backup_in_progress):
    vm_node = rhel_vm_with_dv_running.vmi.node
    with node_mgmt_console(node=vm_node, node_mgmt="drain"):
        wait_for_node_schedulable_status(node=vm_node, status=False)
        yield vm_node


@pytest.fixture(scope="module")
def rhel_vm_with_dv_running_factory(
    admin_client,
    chaos_namespace,
    snapshot_storage_class_name_scope_module,
):
    """
    Factory fixture: create a RHEL VM with a DataVolume.
    Usage in test: vm = rhel_vm_with_dv_running_factory(vm_name="myvm")
    """
    created_vms = []

    def _create(vm_name, rhel_image=Images.Rhel.LATEST_RELEASE_STR):
        vm_generator = create_rhel_vm(
            storage_class=snapshot_storage_class_name_scope_module,
            namespace=chaos_namespace.name,
            vm_name=vm_name,
            dv_name=f"dv-{vm_name}",
            client=admin_client,
            wait_running=True,
            rhel_image=rhel_image,
        )
        vm = vm_generator.__enter__()
        created_vms.append((vm, vm_generator))
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
        )

        return vm

    yield _create

    # Cleanup all created VMs
    for vm, vm_generator in created_vms:
        try:
            vm_generator.__exit__(None, None, None)  # noqa: FCN001
        except Exception:
            LOGGER.exception(f"Failed to cleanup VM {vm.name}")


@pytest.fixture()
def oadp_backup_start_factory(admin_client, chaos_namespace, rhel_vm_with_dv_running_factory):
    """
    Factory fixture: start an OADP backup and yield the backup object.
    """
    created_backups = []

    def _start_backup():
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"backup-{timestamp}"

        backup = VeleroBackup(
            name=backup_name,
            included_namespaces=[chaos_namespace.name],
            client=admin_client,
            snapshot_move_data=True,
            storage_location=BACKUP_STORAGE_LOCATION,
            wait_complete=False,
        )
        backup.__enter__()
        created_backups.append(backup)
        # backup.wait_for_status(status=backup.Backup.Status.INPROGRESS, timeout=TIMEOUT_3MIN)
        return backup

    yield _start_backup

    # Cleanup all created backups
    for backup in created_backups:
        try:
            backup.__exit__(exception_type=None, exception_value=None, traceback=None)
        except Exception:
            LOGGER.exception(f"Failed to cleanup backup {backup.name}")


@pytest.fixture()
def oadp_backup_completed_factory(admin_client, chaos_namespace, rhel_vm_with_dv_running_factory):
    """
    Factory fixture:
    Create an OADP backup and ensure it COMPLETES successfully.
    Any other final status will raise an error.
    """
    created_backups = []

    def _create_and_wait(
        *,
        included_namespaces=None,
        timeout=TIMEOUT_3MIN,
    ):
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"backup-{timestamp}"

        backup = VeleroBackup(
            name=backup_name,
            included_namespaces=included_namespaces or [chaos_namespace.name],
            client=admin_client,
            snapshot_move_data=True,
            storage_location=BACKUP_STORAGE_LOCATION,
            wait_complete=False,  # We wait and control the status. Don't use wait_complete=True
        )
        backup.__enter__()
        created_backups.append(backup)

        terminal_statuses = {
            backup.Backup.Status.COMPLETED,
            backup.Backup.Status.FAILED,
            backup.Backup.Status.PARTIALLYFAILED,
            backup.Backup.Status.FAILEDVALIDATION,
        }

        final_status = None
        for _ in TimeoutSampler(
            wait_timeout=timeout,
            sleep=5,
            func=lambda: backup.instance.status.phase,
        ):
            final_status = backup.instance.status.phase
            if final_status in terminal_statuses:
                break

        if final_status != backup.Backup.Status.COMPLETED:
            raise AssertionError(
                f"OADP Backup {backup.name} did not complete successfully. Final status: {final_status}"
            )

        LOGGER.info(f"OADP Backup {backup.name} completed successfully")
        return backup

    yield _create_and_wait

    # Cleanup
    for backup in created_backups:
        try:
            backup.__exit__(None, None, None)  # noqa: FCN001
        except Exception:
            LOGGER.exception(f"Failed to cleanup backup {backup.name}")


@pytest.fixture()
def oadp_restore_start_factory(admin_client, oadp_backup_completed_factory, deleted_vm):
    """
    Factory fixture:
    Start an OADP restore and return it once it is observed as started.
    """
    created_restores = []

    def _start_restore(
        *,
        backup,
        included_namespaces=None,
        namespace=None,
        timeout=TIMEOUT_3MIN,
    ):
        restore_name = f"restore-{backup.name}"

        restore = VeleroRestore(
            name=restore_name,
            namespace=namespace or backup.namespace,
            included_namespaces=included_namespaces,
            backup_name=backup.name,
            client=admin_client,
            wait_complete=False,
        )
        restore.__enter__()
        created_restores.append(restore)

        for _ in TimeoutSampler(
            wait_timeout=timeout,
            sleep=2,
            func=lambda: restore.instance.status.phase,
        ):
            phase = restore.instance.status.phase
            if phase:
                LOGGER.info(f"Restore {restore.name} entered phase {phase}")
                break

        return restore

    yield _start_restore

    # Cleanup
    for restore in created_restores:
        try:
            restore.__exit__(None, None, None)  # noqa: FCN001
        except Exception:
            LOGGER.exception(f"Failed to cleanup restore {restore.name}")


@pytest.fixture()
def pod_deleting_process_during_oadp_restore(request, admin_client):
    """
    Only create process, not start it. You need to control start timing in the test body.
    """
    pod_prefix = request.param["pod_prefix"]
    namespace_name = request.param["namespace_name"]
    process = create_pod_deleting_process(
        dyn_client=admin_client,
        pod_prefix=pod_prefix,
        namespace_name=namespace_name,
        ratio=request.param["ratio"],
        interval=request.param["interval"],
        max_duration=request.param["max_duration"],
    )
    # LOGGER.info("Pod deleting process for {pod_prefix} in {namespace_name} start...")
    # process.start()
    yield {
        "process": process,
        "namespace_name": namespace_name,
        "pod_prefix": pod_prefix,
    }

    # Teardown: terminate the subprocess
    terminate_process(process=process)

    # Ensure the subprocess has fully exited
    process.join(timeout=10)
    if process.is_alive():
        LOGGER.warning(f"Pod deleting process for {pod_prefix} in {namespace_name} did not exit within 10 seconds")
    else:
        LOGGER.info(f"Pod deleting process for {pod_prefix} in {namespace_name} terminated successfully")


# @pytest.fixture()
# def deleted_vm():
#     """
#     Fixture to delete a given VM and ensure it is deleted.
#     Usage in test: delete_vm(vm)
#     """
#
#     def _delete(vm):
#         LOGGER.info(f"Deleting VM {vm.name} ...")
#         success = vm.delete(wait=True, timeout=TIMEOUT_5MIN)
#         assert success, f"VM {vm.name} was not deleted"
#         LOGGER.info(f"VM {vm.name} deleted successfully.")
#
#     return _delete
