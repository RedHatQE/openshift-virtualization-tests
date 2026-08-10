"""
Velero Backup Hook Opt-Out Tests

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/
sig-storage/remove-velero-hooks-stp.md
Jira: https://redhat.atlassian.net/browse/CNV-79727 # <skip-jira-utils-check>
"""

import logging

import pytest

from tests.data_protection.oadp.utils import assert_velero_backup_hooks_not_injected
from utilities.oadp import VeleroBackup

LOGGER = logging.getLogger(__name__)


class TestVeleroBackupHookOptOut:
    """
    Tests for Velero backup hook opt-out.

    The skip-backup-hooks annotation is intended for metadata-only backup workflows where
    third-party solutions handle the actual data protection. These tests verify that
    freeze/unfreeze hooks are not injected and that Velero backup completes when the
    annotation is set.

    Preconditions:
        - Under-test VM with ``kubevirt.io/skip-backup-hooks`` set to ``"true"``
    """

    @pytest.mark.polarion("CNV-16267")
    def test_backup_paused_vm_hooks_disabled(
        self,
        admin_client,
        namespace_for_hooks_backup,
        paused_rhel_vm_with_hooks_opt_out,
    ):
        """
        Test that backup of paused VM completes with hooks disabled.

        Preconditions:
            - Under-test VM with ``kubevirt.io/skip-backup-hooks`` set to ``"true"``, paused

        Steps:
            1. Run Velero backup
            2. Inspect virt-launcher pod for Velero hook annotations

        Expected:
            - No freeze/unfreeze hooks are injected on the virt-launcher pod
            - Backup completes successfully
        """
        with VeleroBackup(
            name="backup-paused-optout",
            client=admin_client,
            included_namespaces=[namespace_for_hooks_backup.name],
            teardown=True,
        ) as backup:
            assert_velero_backup_hooks_not_injected(vm=paused_rhel_vm_with_hooks_opt_out, admin_client=admin_client)
            LOGGER.info(f"Backup {backup.name} completed for paused VM with opt-out annotation")

    @pytest.mark.polarion("CNV-16268")
    def test_backup_running_vm_hooks_disabled(
        self,
        admin_client,
        namespace_for_hooks_backup,
        rhel_vm_with_hooks_opt_out,
    ):
        """
        Test that backup of a running VM completes with hooks disabled.

        Preconditions:
            - Under-test VM with ``kubevirt.io/skip-backup-hooks`` set to ``"true"``, running

        Steps:
            1. Run Velero backup
            2. Inspect virt-launcher pod for Velero hook annotations

        Expected:
            - No freeze/unfreeze hooks are injected on the virt-launcher pod
            - Backup completes successfully
        """
        with VeleroBackup(
            name="backup-hooks-opt-out",
            client=admin_client,
            included_namespaces=[namespace_for_hooks_backup.name],
            teardown=True,
        ) as backup:
            assert_velero_backup_hooks_not_injected(vm=rhel_vm_with_hooks_opt_out, admin_client=admin_client)
            LOGGER.info(f"Backup {backup.name} completed for running VM with opt-out annotation")
