import logging

import pytest

from utilities.constants import TIMEOUT_10MIN

LOGGER = logging.getLogger(__name__)


@pytest.mark.destructive
@pytest.mark.chaos
class TestVMChaosNodeDuringOADPBackup:
    @pytest.mark.polarion("CNV-12011")
    def test_reboot_vm_node_during_backup(
        self,
        rhel_vm_with_dv_running,
        oadp_backup_in_progress,
        rebooted_vm_source_node,
    ):
        """
        Reboot the worker node where the VM is located during OADP backup using DataMover.
        Validate that backup eventually PartiallyFailed.
        """
        oadp_backup_in_progress.wait_for_status(
            status=oadp_backup_in_progress.Backup.Status.PARTIALLYFAILED, timeout=TIMEOUT_10MIN
        )

    @pytest.mark.polarion("CNV-12020")
    def test_drain_vm_node_during_backup(
        self,
        oadp_backup_in_progress,
        drained_vm_source_node,
    ):
        """
        Drain the worker node where the VM is located during OADP backup using DataMover.
        Validate that backup eventually Completed.
        """
        LOGGER.info(
            f"Waiting for backup to reach '{oadp_backup_in_progress.Backup.Status.COMPLETED}' during node drain."
        )
        oadp_backup_in_progress.wait_for_status(
            status=oadp_backup_in_progress.Backup.Status.COMPLETED, timeout=TIMEOUT_10MIN
        )

    @pytest.mark.polarion("CNV-12016")
    def test_cordon_off_vm_node_during_backup(
        self,
        oadp_backup_in_progress,
        cordoned_vm_source_node,
    ):
        """
        Cordon off the worker node where the VM is located during OADP backup using DataMover.
        Validate that backup eventually Completed.
        """
        LOGGER.info(
            f"Waiting for backup to reach '{oadp_backup_in_progress.Backup.Status.COMPLETED}' during node cordon."
        )
        oadp_backup_in_progress.wait_for_status(
            status=oadp_backup_in_progress.Backup.Status.COMPLETED, timeout=TIMEOUT_10MIN
        )
