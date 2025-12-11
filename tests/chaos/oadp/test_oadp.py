import logging

import pytest

from tests.chaos.utils import pod_deleting_process_recover
from tests.os_params import RHEL_LATEST
from utilities.constants import TIMEOUT_10MIN

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
                "pod_prefix": "node-agent",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 60,
            },
            "PartiallyFailed",
            marks=pytest.mark.polarion("CNV-12022"),
            id="node-agent",
        ),
        pytest.param(
            {
                "pod_prefix": "openshift-adp-controller-manager",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 60,
            },
            "Completed",
            marks=pytest.mark.polarion("CNV-12024"),
            id="openshift-oadp-controller-manager",
        ),
        pytest.param(
            {
                "pod_prefix": "velero",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 60,
            },
            "Failed",
            marks=pytest.mark.polarion("CNV-12026"),
            id="velero",
        ),
        pytest.param(
            {
                "pod_prefix": "minio",
                "namespace_name": "minio",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 60,
            },
            "Failed",
            marks=pytest.mark.polarion("CNV-12028"),
            id="minio",
        ),
    ],
    indirect=["pod_deleting_process"],
)
def test_delete_pods_during_backup(
    admin_client,
    chaos_namespace,
    rhel_vm_with_dv_running_factory,
    oadp_backup_in_progress_factory,
    pod_deleting_process,
    expected_status,
):
    """
    Delete various OADP-related pods during an in-progress Velero backup
    and verify the backup reaches its expected final status.
    """
    # Create a VM so that OADP backup has resources to process
    _ = rhel_vm_with_dv_running_factory(vm_name="rhel-vm")
    backup = oadp_backup_in_progress_factory()
    final_status = backup.wait_for_status()

    assert final_status == getattr(backup.Backup.Status, expected_status.upper()), (
        f"Expected {expected_status}, got {final_status}"
    )

    # Verify recovery if applicable
    pod_deleting_process_recover(
        resource="deployment",
        namespace=["namespace_name"],
        pod_prefix=pod_deleting_process["pod_prefix"],
    )
