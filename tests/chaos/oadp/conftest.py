import datetime
import logging

import pytest
from kubernetes.client import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.namespace import Namespace
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler

from tests.chaos.utils import (
    create_pod_deleting_thread,
    pod_deleting_process_recover,
)
from utilities.constants import (
    BACKUP_STORAGE_LOCATION,
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    Images,
)
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import OADP_BACKUP_TERMINAL_STATUSES, VeleroBackup, VeleroRestore, create_rhel_vm
from utilities.storage import write_file
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = 5


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

    final_status = None

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: backup.instance.status.phase,
        ):
            if sample in OADP_BACKUP_TERMINAL_STATUSES:
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
        except ResourceNotFoundError, ValueError, TypeError:
            LOGGER.error(
                f"Recovery failed for prefix "
                f"{pod_deleting_thread_during_oadp_operations['pod_prefix']} "
                f"in namespace {pod_deleting_thread_during_oadp_operations['namespace_name']}"
            )
            raise


@pytest.fixture(scope="module")
def oadp_backup_completed(admin_client, chaos_namespace, rhel_vm_with_dv_running):
    """
    Create a Velero backup and wait until it reaches Completed phase.

    This fixture:
    - creates backup
    - waits for completion
    - asserts Completed
    - yields backup object
    - deletes backup automatically on teardown
    """

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"backup-{timestamp}"

    with VeleroBackup(
        name=backup_name,
        included_namespaces=[chaos_namespace.name],
        snapshot_move_data=True,
        storage_location=BACKUP_STORAGE_LOCATION,
        client=admin_client,
        wait_complete=False,  # we wait manually
    ) as backup:
        final_phase = None

        for phase in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=10,
            func=lambda: backup.instance.status.phase,
        ):
            final_phase = phase
            LOGGER.info(f"Backup {backup.name} phase: {phase}")

            if phase in OADP_BACKUP_TERMINAL_STATUSES:
                break

        assert final_phase == backup.Backup.Status.COMPLETED, f"Backup {backup.name} ended with phase {final_phase}"

        yield backup


@pytest.fixture()
def chaos_vms_cleanup(admin_client, chaos_namespace):
    namespace_name = chaos_namespace.name

    LOGGER.info(f"Fetching all VMs in namespace {namespace_name}")

    vms = list(VirtualMachine.get(client=admin_client, namespace=namespace_name))

    if vms:
        LOGGER.info(f"VMs in namespace {namespace_name}: {[vm.name for vm in vms]}")
    else:
        LOGGER.info(f"No VMs found in namespace {namespace_name}")

    for vm in vms:
        LOGGER.info(f"Deleting VM {vm.name}")
        vm.delete(wait=False)

    def all_vms_deleted():
        remaining = list(VirtualMachine.get(client=admin_client, namespace=namespace_name))

        if not remaining:
            return True

        LOGGER.info(f"Remaining VMs: {[vm.name for vm in remaining]}")
        return False

    for _ in TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=POLL_INTERVAL,
        func=all_vms_deleted,
    ):
        if all_vms_deleted():
            break

    LOGGER.info(f"All VMs in namespace {namespace_name} deleted")


@pytest.fixture()
def deleted_namespace(admin_client, chaos_vms_cleanup):
    """
    General fixture to delete any namespace by name and wait for its removal.
    """

    def _delete(namespace_name):
        LOGGER.info(f"Deleting namespace {namespace_name} ...")

        try:
            ns = next(Namespace.get(client=admin_client, name=namespace_name), None)
            if ns.exists:
                ns.delete()
                LOGGER.info(f"Namespace {namespace_name} deletion triggered")
            else:
                LOGGER.info(f"Namespace {namespace_name} does not exist, skipping delete")
        except ApiException as error:
            LOGGER.error(f"Failed to delete namespace {namespace_name}", exc_info=True)
            raise RuntimeError(f"Namespace delete failed for {namespace_name}") from error

        def namespace_removed():
            ns = Namespace(name=namespace_name, client=admin_client)
            if ns.exists:
                LOGGER.info(f"Namespace {namespace_name} still exists")
                return False
            return True

        for removed in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=POLL_INTERVAL,
            func=namespace_removed,
        ):
            if removed:
                LOGGER.info(f"Namespace {namespace_name} confirmed removed")
                break

    return _delete


@pytest.fixture()
def deleted_chaos_namespace(chaos_namespace, deleted_namespace, chaos_vms_cleanup):
    """
    Specialized fixture to delete the chaos namespace using the general fixture.
    """
    deleted_namespace(namespace_name=chaos_namespace.name)


@pytest.fixture()
def oadp_restore_started(admin_client, oadp_backup_completed, deleted_chaos_namespace):
    restore_name = f"restore-{oadp_backup_completed.name}"

    with VeleroRestore(
        name=restore_name,
        namespace=oadp_backup_completed.namespace,
        backup_name=oadp_backup_completed.name,
        client=admin_client,
        wait_complete=False,
    ) as restore:
        yield restore


@pytest.fixture()
def restore_with_pod_deletion_orchestration(
    oadp_restore_started,
    pod_deleting_thread_during_oadp_operations,
):
    """
    Orchestrate OADP restore while continuously deleting target pods.

    Flow:
    - Start pod deleting thread
    - Wait for restore to reach terminal phase
    - Yield final restore phase
    - Recover deleted workloads (Deployment / DaemonSet)
    """

    restore = oadp_restore_started

    thread = pod_deleting_thread_during_oadp_operations["thread"]
    namespace = pod_deleting_thread_during_oadp_operations["namespace_name"]
    pod_prefix = pod_deleting_thread_during_oadp_operations["pod_prefix"]

    # Start chaos
    thread.start()

    terminal_statuses = {
        restore.Status.COMPLETED,
        restore.Status.FAILED,
    }

    final_status = None

    try:
        for phase in TimeoutSampler(
            wait_timeout=TIMEOUT_3MIN,
            sleep=5,
            func=lambda: restore.instance.status.phase,
        ):
            if phase:
                LOGGER.info(f"Restore {restore.name} phase: {phase}")
                if phase in terminal_statuses:
                    final_status = phase
                    break

        yield final_status

    finally:
        pod_deleting_thread_during_oadp_operations["stop_event"].set()
        # Recovery only — thread teardown handled by pod_deleting_thread fixture
        pod_deleting_process_recover(
            resources=[Deployment, DaemonSet],
            namespace=namespace,
            pod_prefix=pod_prefix,
        )
