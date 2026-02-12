import logging

import pytest

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


@pytest.mark.destructive
@pytest.mark.tier3
@pytest.mark.chaos
@pytest.mark.parametrize(
    ("pod_deleting_thread_during_oadp_operations", "expected_status"),
    [
        pytest.param(
            {
                "pod_prefix": "openshift-adp-controller-manager",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 20,
                "max_duration": 180,
            },
            "Completed",
            marks=pytest.mark.polarion("CNV-12024"),
            id="openshift-adp-controller-manager",
        ),
        pytest.param(
            {
                "pod_prefix": "velero",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 30,
                "max_duration": 300,
            },
            "Failed",
            marks=pytest.mark.polarion("CNV-12026"),
            id="velero",
        ),
        pytest.param(
            {
                "pod_prefix": "node-agent",
                "namespace_name": "openshift-adp",
                "ratio": 1.0,
                "interval": 10,
                "max_duration": 180,
            },
            "PartiallyFailed",
            marks=pytest.mark.polarion("CNV-12022"),
            id="node-agent",
        ),
    ],
    indirect=[
        "pod_deleting_thread_during_oadp_operations",
    ],
)
def test_delete_pods_during_backup(
    backup_with_pod_deletion_orchestration,
    expected_status,
):
    """
    This test verifies OADP Backup resilience under control-plane disruptions.

    Test flow:
    1. Create a healthy VM and persist data inside the guest.
    2. Trigger an OADP Backup.
    3. Start a background process that continuously deletes critical OADP-related
       pods (e.g. controller-manager, node-agent, velero, minio) while the Backup
       is in progress.
    4. Wait for the OADP Backup to reach a terminal state.
    5. Stop the pod deletion process once the Backup finishes.
    6. Verify the final Backup status matches the expected result.
    """

    assert backup_with_pod_deletion_orchestration == expected_status, (
        f"Expected backup status {expected_status}, got {backup_with_pod_deletion_orchestration}"
    )
