"""
Velero Backup Hook Opt-Out Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/remove-velero-hooks-stp.md
Jira: https://redhat.atlassian.net/browse/CNV-79727 # <skip-jira-utils-check>
"""

import logging

import pytest

from tests.data_protection.oadp.utils import get_velero_backup_logs
from utilities.constants.timeouts import TIMEOUT_15MIN
from utilities.oadp import VeleroBackup
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)

HOOK_LOG_PATTERN = "freeze"

pytestmark = pytest.mark.usefixtures("skip_if_no_storage_class_for_snapshot")


class TestVeleroBackupHookOptOut:
    """
    Tests for Velero backup hook opt-out with backup/restore operations.

    Preconditions:
        - VM with backup hooks disabled
    """

    @pytest.mark.polarion("CNV-16267")
    @pytest.mark.s390x
    def test_backup_paused_vm_hooks_disabled(
        self,
        admin_client,
        namespace_for_backup,
        rhel_vm_with_hooks_opt_out,
    ):
        """
        Test that backup of paused VM completes with hooks disabled.

        Preconditions:
            - VM with backup hooks disabled, paused

        Steps:
            1. Run Velero backup

        Expected:
            - Backup completes successfully without freeze/unfreeze hook execution
        """
        rhel_vm_with_hooks_opt_out.vmi.pause(wait=True)
        LOGGER.info(f"VM {rhel_vm_with_hooks_opt_out.name} paused")

        with VeleroBackup(
            name="backup-paused-optout",
            client=admin_client,
            included_namespaces=[namespace_for_backup.name],
        ) as backup:
            LOGGER.info(f"Backup {backup.name} completed for paused VM with opt-out annotation")

        backup_logs = get_velero_backup_logs(backup_name=backup.name, client=admin_client)
        assert HOOK_LOG_PATTERN not in backup_logs.lower(), (
            f"Backup {backup.name} logs contain hook entries but hooks should be disabled"
        )

    @pytest.mark.polarion("CNV-16268")
    @pytest.mark.s390x
    @pytest.mark.usefixtures("velero_restore_vm_with_hooks_opt_out")
    def test_full_backup_restore_hooks_disabled(
        self,
        admin_client,
        rhel_vm_with_hooks_opt_out,
        velero_backup_vm_with_hooks_opt_out,
    ):
        """
        Test that full backup/restore cycle completes with hooks disabled.

        Preconditions:
            - Running VM with backup hooks disabled

        Steps:
            1. Run Velero backup
            2. Delete VM and namespace
            3. Restore from backup

        Expected:
            - VM is restored and running after backup/restore cycle without hook execution
        """
        wait_for_running_vm(
            vm=rhel_vm_with_hooks_opt_out,
            wait_until_running_timeout=TIMEOUT_15MIN,
            wait_for_interfaces=False,
            check_ssh_connectivity=False,
        )
        backup_logs = get_velero_backup_logs(
            backup_name=velero_backup_vm_with_hooks_opt_out.name,
            client=admin_client,
        )
        assert HOOK_LOG_PATTERN not in backup_logs.lower(), (
            f"Backup {velero_backup_vm_with_hooks_opt_out.name} logs contain hook entries but hooks should be disabled"
        )
