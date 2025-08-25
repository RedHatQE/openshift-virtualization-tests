import logging

import pytest
from ocp_resources.utils.resource_constants import ResourceConstants

from tests.os_params import RHEL_LATEST
from utilities.constants import TIMEOUT_10MIN

LOGGER = logging.getLogger(__name__)


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
    chaos_namespace,
    oadp_backup_in_progress,
    rebooted_vm_source_node,
):
    """
    Reboot the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually PartiallyFailed.
    """

    LOGGER.info("Waiting for backup to reach 'PartiallyFailed' status after node recovery")
    oadp_backup_in_progress.wait_for_status(
        status=ResourceConstants.Backup.Status.PARTIALLYFAILED, timeout=TIMEOUT_10MIN
    )
