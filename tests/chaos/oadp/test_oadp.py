import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.utils.resource_constants import ResourceConstants

from utilities.constants import TIMEOUT_10MIN, TIMEOUT_40MIN, Images
from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)


@pytest.mark.chaos
@pytest.mark.volume_mode("block")
@pytest.mark.parametrize(
    "rhel_vm_with_dv_running",
    [
        pytest.param(
            {
                "vm_name": "vm-12011",
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-12011"),
        ),
    ],
    indirect=True,
)
def test_reboot_vm_node_during_backup(
    chaos_namespace,
    rhel_vm_with_dv_running,
    oadp_backup_in_progress,
    rebooted_vm_source_node,
):
    """
    Reboot the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Failed or PartiallyFailed.
    """

    LOGGER.info("Waiting for backup to reach 'PartiallyFailed' status after node recovery")
    oadp_backup_in_progress.wait_for_status(status="PartiallyFailed", timeout=TIMEOUT_10MIN)


@pytest.mark.chaos
@pytest.mark.parametrize(
    "rhel_vm_with_dv_running",
    [
        pytest.param(
            {
                "vm_name": "vm-12021-drain",
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-12016"),
        ),
    ],
    indirect=True,
)
def test_drain_vm_node_during_backup(
    chaos_namespace,
    oadp_backup_in_progress,
    drain_vm_source_node,
):
    """
    Drain the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Completed.
    """
    jira_id = "CNV-67519"
    if is_jira_open(jira_id):
        oadp_backup_in_progress.wait_for_status(
            status=ResourceConstants.Backup.Status.PARTIALLYFAILED, timeout=TIMEOUT_40MIN
        )
        pytest.xfail(f"Known bug {jira_id} still affects this test")
    else:
        oadp_backup_in_progress.wait_for_status(status=ResourceConstants.Backup.Status.COMPLETED, timeout=TIMEOUT_10MIN)
