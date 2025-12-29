import logging

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from timeout_sampler import TimeoutSampler

from tests.chaos.utils import pod_deleting_process_recover, wait_for_restored_vmi
from tests.os_params import RHEL_LATEST
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_10MIN
from utilities.oadp import check_file_in_vm

LOGGER = logging.getLogger(__name__)


@pytest.mark.destructive
@pytest.mark.chaos
@pytest.mark.parametrize(
    "rhel_vm_with_dv_running",
    [
        pytest.param(
            {
                "vm_name": "vm-node-reboot-12011",
                "rhel_image": RHEL_LATEST["image_name"],
            },
            marks=pytest.mark.polarion("CNV-12011"),
        ),
    ],
    indirect=True,
)
def test_reboot_vm_node_during_backup(
    oadp_backup_in_progress,
    rebooted_vm_source_node,
):
    """
    Reboot the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually PartiallyFailed.
    """

    LOGGER.info(
        f"Waiting for backup to reach "
        f"'{oadp_backup_in_progress.Backup.Status.PARTIALLYFAILED}' status after node recovery"
    )
    oadp_backup_in_progress.wait_for_status(
        status=oadp_backup_in_progress.Backup.Status.PARTIALLYFAILED, timeout=TIMEOUT_10MIN
    )


@pytest.mark.destructive
@pytest.mark.chaos
@pytest.mark.parametrize(
    "rhel_vm_with_dv_running",
    [
        pytest.param(
            {
                "vm_name": "vm-node-drain-12020",
                "rhel_image": RHEL_LATEST["image_name"],
            },
            marks=pytest.mark.polarion("CNV-12020"),
        ),
    ],
    indirect=True,
)
def test_drain_vm_node_during_backup(
    oadp_backup_in_progress,
    drain_vm_source_node,
):
    """
    Drain the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Completed.
    """
    LOGGER.info(f"Waiting for backup to reach '{oadp_backup_in_progress.Backup.Status.COMPLETED}' during node drain.")
    oadp_backup_in_progress.wait_for_status(
        status=oadp_backup_in_progress.Backup.Status.COMPLETED, timeout=TIMEOUT_10MIN
    )


@pytest.mark.chaos
@pytest.mark.parametrize(
    "pod_deleting_process, expected_status",
    [
        pytest.param(
            {
                "pod_prefix": "minio",
                "namespace_name": "minio",
                "ratio": 1.0,
                "interval": 180,
                "max_duration": 360,
            },
            "FailedValidation",
            marks=pytest.mark.polarion("CNV-12028"),
            id="minio",
        ),
        pytest.param(
            {
                "pod_prefix": "velero",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 30,
                "max_duration": 300,
            },
            "Completed",
            marks=pytest.mark.polarion("CNV-12026"),
            id="velero",
        ),
        pytest.param(
            {
                "pod_prefix": "openshift-adp-controller-manager",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 20,
                "max_duration": 300,
            },
            "Completed",
            marks=pytest.mark.polarion("CNV-12024"),
            id="openshift-adp-controller-manager",
        ),
        pytest.param(
            {
                "pod_prefix": "node-agent",
                "namespace_name": "openshift-adp",
                "ratio": 1,
                "interval": 10,
                "max_duration": 300,
            },
            "PartiallyFailed",
            marks=pytest.mark.polarion("CNV-12022"),
            id="node-agent",
        ),
    ],
    indirect=["pod_deleting_process"],
)
def test_delete_pods_during_backup(
    admin_client,
    chaos_namespace,
    rhel_vm_with_dv_running_factory,
    oadp_backup_start_factory,
    pod_deleting_process,
    expected_status,
):
    """
    Delete various OADP-related pods during an in-progress Velero backup
    and verify the backup reaches its expected final status.
    """
    # Each test case creates its own VM to ensure isolation and OADP backup has resources to process
    _ = rhel_vm_with_dv_running_factory(vm_name="rhel-vm")
    backup = oadp_backup_start_factory()

    # Wait until backup reaches any terminal state
    terminal_statuses = {
        backup.Backup.Status.COMPLETED,
        backup.Backup.Status.FAILED,
        backup.Backup.Status.PARTIALLYFAILED,
        backup.Backup.Status.FAILEDVALIDATION,
    }

    final_status = None
    for _ in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=5,
        func=lambda: backup.instance.status.phase,
    ):
        final_status = backup.instance.status.phase
        if final_status in terminal_statuses:
            break

    assert final_status == expected_status, f"Expected backup status {expected_status}, got {final_status}"

    # Verify recovery if applicable
    pod_deleting_process_recover(
        resources=[Deployment, DaemonSet],
        namespace=pod_deleting_process["namespace_name"],
        pod_prefix=pod_deleting_process["pod_prefix"],
    )


@pytest.mark.chaos
@pytest.mark.parametrize(
    "pod_deleting_process_during_oadp_restore, expected_status",
    [
        # pytest.param(
        #     {
        #         "pod_prefix": "minio",
        #         "namespace_name": "minio",
        #         "ratio": 1.0,
        #         "interval": 180,
        #         "max_duration": 360,
        #     },
        #     "Failed",
        #     marks=pytest.mark.polarion("CNV-12029"),
        #     id="minio",
        # ),
        # pytest.param(
        #     {
        #         "pod_prefix": "velero",
        #         "namespace_name": "openshift-adp",
        #         "ratio": 1.0,
        #         "interval": 30,
        #         "max_duration": 300,
        #     },
        #     "Completed",
        #     marks=pytest.mark.polarion("CNV-12027"),
        #     id="velero",
        # ),
        pytest.param(
            {
                "pod_prefix": "openshift-adp-controller-manager",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 120,
            },
            "Completed",
            marks=pytest.mark.polarion("CNV-12025"),
            id="openshift-adp-controller-manager",
        ),
        # pytest.param(
        #     {
        #         "pod_prefix": "node-agent",
        #         "namespace_name": "openshift-adp",
        #         "ratio": 1,
        #         "interval": 10,
        #         "max_duration": 300,
        #     },
        #     "Completed",
        #     marks=pytest.mark.polarion("CNV-12023"),
        #     id="node-agent",
        # ),
    ],
    indirect=["pod_deleting_process_during_oadp_restore"],
)
def test_delete_pods_during_restore(
    admin_client,
    chaos_namespace,
    rhel_vm_with_dv_running_factory,
    oadp_backup_completed_factory,
    oadp_restore_start_factory,
    pod_deleting_process_during_oadp_restore,
    expected_status,
):
    """
    This test verifies OADP restore resilience under control-plane disruptions.

    High-level flow:
    1. Create a healthy VM and persist data inside the guest.
    2. Take a successful OADP backup from a stable cluster state.
    3. Explicitly stop and delete the original VM to ensure the restore path
       recreates the VM from backup artifacts.
    4. Start a background process that continuously deletes critical OADP-related
       pods (e.g. controller-manager, node-agent，velero，minio) while the restore is in progress.
    5. Trigger the restore and wait for it to reach a terminal state.
    6. If restore succeeds:
       - Wait for the restore controller to recreate the VM resource.
       - Wait for the VM to reach Running state.
       - Verify guest data integrity.
    """
    vm = rhel_vm_with_dv_running_factory(vm_name="rhel-vm-restore")
    vm_name = vm.name
    check_file_in_vm(vm=vm)

    # Create the Backup from a healthy VM/Cluster state.
    backup = oadp_backup_completed_factory()

    # Delete the original VM
    vm.stop(wait=True)
    assert vm.delete(wait=True, timeout=TIMEOUT_5MIN), "VM was not deleted"

    # Start pod deletion process
    process = pod_deleting_process_during_oadp_restore["process"]
    process.start()

    # Trigger Restore
    restore = oadp_restore_start_factory(backup=backup)

    terminal_statuses = {
        restore.Status.COMPLETED,
        restore.Status.FAILED,
    }

    final_status = None
    for _ in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=5,
        func=lambda: restore.instance.status.phase,
    ):
        final_status = restore.instance.status.phase
        if final_status in terminal_statuses:
            break

    LOGGER.info(f"Restore {restore.name} finished with status: {final_status}")

    assert final_status == expected_status

    if final_status == restore.Status.COMPLETED:
        LOGGER.info("Waiting for restored VM to be created automatically by restore controller")
        # restored_vm = None
        # for vm_obj in TimeoutSampler(
        #     wait_timeout=TIMEOUT_5MIN,
        #     sleep=5,
        #     func=lambda: get_vm_from_restore(
        #         admin_client=admin_client,
        #         namespace=chaos_namespace.name,
        #         vm_name_prefix="rhel-vm-restore",
        #         timeout=120,
        #     ),
        # ):
        #     if vm_obj:
        #         restored_vm = vm_obj
        #         break

        # restored_vm = get_vm_from_restore(
        #     admin_client=admin_client,
        #     namespace=chaos_namespace.name,
        #     vm_name_prefix="rhel-vm-restore",
        #     timeout=240,
        #     sleep=5,
        # )

        restored_vmi = wait_for_restored_vmi(
            admin_client=admin_client,
            namespace=chaos_namespace.name,
            vmi_name_prefix="rhel-vm-restore",
            timeout=TIMEOUT_5MIN,
        )

        assert restored_vmi is not None, f"Restored VMI {vm_name} was not found"

        # wait_for_running_vm(vm=restored_vm)

        check_file_in_vm(vm=restored_vmi)

    # Verify recovery if applicable
    pod_deleting_process_recover(
        resources=[Deployment, DaemonSet],
        namespace=pod_deleting_process_during_oadp_restore["namespace_name"],
        pod_prefix=pod_deleting_process_during_oadp_restore["pod_prefix"],
    )
