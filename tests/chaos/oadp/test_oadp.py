import logging

import pytest


from tests.os_params import RHEL_LATEST
from ocp_resources.datavolume import DataVolume
from utilities.constants import TIMEOUT_10MIN, Images


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
@pytest.mark.chaos
@pytest.mark.parametrize(
    "rhel_vm_with_dv_running",
    [
        pytest.param(
            {
                "vm_name": "vm-node-cordon-12016",
                "rhel_image": RHEL_LATEST["image_name"],
            },
            marks=pytest.mark.polarion("CNV-12016"),
        ),
    ],
    indirect=True,
)
def test_cordon_off_vm_node_during_backup(
    oadp_backup_in_progress,
    cordon_vm_source_node,
):
    """
    Cordon off the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Completed.
    """
    oadp_backup_in_progress.wait_for_status(status=oadp_backup_in_progress.Backup.Status.COMPLETED, timeout=TIMEOUT_10MIN)
