import logging

import pytest
from ocp_resources.datavolume import DataVolume

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5MIN, TIMEOUT_10MIN, Images
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.oadp import VeleroBackup
from utilities.virt import node_mgmt_console, wait_for_node_schedulable_status

LOGGER = logging.getLogger(__name__)


@pytest.mark.chaos
@pytest.mark.parametrize(
    "vm_with_datavolume_template",
    [
        pytest.param(
            {
                "vm_name": "vm-12011",
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-12011"),
        ),
    ],
    indirect=True,
)
def test_reboot_vm_node_during_backup(
    admin_client,
    chaos_namespace,
    snapshot_storage_class_name_scope_module,
    vm_with_datavolume_template,
    workers_utility_pods,
):
    """
    Reboot the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Failed or PartiallyFailed.
    """

    vm = vm_with_datavolume_template
    vm.vmi.wait_until_running(timeout=TIMEOUT_3MIN)
    vm_node = vm.vmi.node
    backup_name = "backup-node-reboot"
    with VeleroBackup(
        name=backup_name,
        included_namespaces=[chaos_namespace.name],
        snapshot_move_data=True,
        storage_location="dpa-1",
        wait_complete=False,
    ) as backup:
        LOGGER.info(f"Created backup: {backup_name}. Waiting for it to enter 'InProgress'...")
        backup.wait_for_status(status="InProgress", timeout=TIMEOUT_3MIN)

        LOGGER.info(f"Rebooting node {vm_node.name}")
        ExecCommandOnPod(utility_pods=workers_utility_pods, node=vm_node).exec(
            command="shutdown -r now", ignore_rc=True
        )
        wait_for_node_status(node=vm_node, status=False, wait_timeout=TIMEOUT_5MIN)

        LOGGER.info(f"Waiting for node {vm_node.name} to come back online")
        wait_for_node_status(node=vm_node, status=True, wait_timeout=TIMEOUT_5MIN)

        LOGGER.info("Waiting for backup to reach 'PartiallyFailed' status after node recovery")
        backup.wait_for_status(status="PartiallyFailed", timeout=TIMEOUT_10MIN)


@pytest.mark.chaos
@pytest.mark.parametrize(
    "vm_with_datavolume_template",
    [
        pytest.param(
            {
                "vm_name": "vm-12016",
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-12016"),
        ),
    ],
    indirect=True,
)
def test_cordon_off_vm_node_during_backup(
    admin_client,
    chaos_namespace,
    snapshot_storage_class_name_scope_module,
    vm_with_datavolume_template,
):
    """
    Cordon off the worker node where the VM is located during OADP backup using DataMover.
    Validate that backup eventually Completed.
    """

    vm = vm_with_datavolume_template
    vm.vmi.wait_until_running(timeout=TIMEOUT_3MIN)
    vm_node = vm.vmi.node
    backup_name = "backup-node-cordon"
    with VeleroBackup(
        name=backup_name,
        included_namespaces=[chaos_namespace.name],
        snapshot_move_data=True,
        storage_location="dpa-1",
        wait_complete=False,
    ) as backup:
        LOGGER.info(f"Created backup: {backup_name}. Waiting for it to enter 'InProgress'...")
        backup.wait_for_status(status="InProgress", timeout=TIMEOUT_3MIN)

        with node_mgmt_console(node=vm_node, node_mgmt="cordon"):
            wait_for_node_schedulable_status(node=vm_node, status=False, timeout=TIMEOUT_5MIN)
            backup.wait_for_status(status="Completed", timeout=TIMEOUT_10MIN)
