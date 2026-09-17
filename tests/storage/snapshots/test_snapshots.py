import hashlib
import logging
from time import monotonic

import pytest
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.snapshots.utils import restore_vm_within_deadline, run_parallel
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.storage import assert_guest_disk_count
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.mark.tier3
@pytest.mark.conformance
class TestRestoreMultiDiskPerformance:
    """
    Snapshot restore performance tests for VMs with multiple disks.

    Jira: https://redhat.atlassian.net/browse/CNV-88908  # <skip-jira-utils-check>

    Preconditions:
        - VolumeSnapshot-capable StorageClass available
        - Fedora golden image DataSource available
    """

    @pytest.mark.polarion("CNV-16805")
    def test_restore_single_vm_with_4_disks_completes_within_five_minutes(self, request, vm_with_4_disks):
        """
        Test that restoring a snapshot of a single VM with 4 disks completes within 5 minutes.

        Preconditions:
            - 1 running Fedora VM with 4 disk devices (1 boot from golden image DataSource + 3 blank DVs)
            - VM snapshot taken and ready to use
            - VM stopped before restore

        Steps:
            1. Create a snapshot of the under-test VM
            2. Initiate restore within a 5-minute deadline
            3. Start the restored VM
            4. Verify the restored VM guest disk count matches the VM spec

        Expected:
            - Restore completed successfully within 5 minutes and the restored VM
              reports the same number of disks as the VM spec
        """
        admin_client = vm_with_4_disks.client
        if vm_with_4_disks.ready:
            vm_with_4_disks.stop(wait=True)

        nodeid_hash = hashlib.md5(request.node.nodeid.encode()).hexdigest()[:8]
        snapshot_name = f"snapshot-{vm_with_4_disks.name}-{nodeid_hash}"
        with VirtualMachineSnapshot(
            name=snapshot_name,
            namespace=vm_with_4_disks.namespace,
            vm_name=vm_with_4_disks.name,
            client=admin_client,
        ) as snapshot:
            snapshot.deploy()
            snapshot.wait_snapshot_done()

            deadline = monotonic() + TIMEOUT_5MIN
            restore = VirtualMachineRestore(
                name=f"restore-{vm_with_4_disks.name}",
                namespace=vm_with_4_disks.namespace,
                vm_name=vm_with_4_disks.name,
                snapshot_name=snapshot.name,
                client=admin_client,
            )

            restore_vm_within_deadline(restore=restore, deadline=deadline)

            restored_vm = VirtualMachineForTests(
                name=vm_with_4_disks.name,
                namespace=vm_with_4_disks.namespace,
                client=admin_client,
                generate_unique_name=False,
            )
            running_vm(vm=restored_vm)
            assert_guest_disk_count(vm=restored_vm)

    @pytest.mark.polarion("CNV-16806")
    @pytest.mark.parametrize(
        "snapshot_and_restore_vms",
        [{"count": 4}],
        indirect=True,
    )
    def test_restore_four_vms_with_4_disks_completes_within_five_minutes(self, snapshot_and_restore_vms):
        """
        Test that restoring snapshots of 4 VMs (each with 4 disks) in parallel completes within 5 minutes per VM.

        Preconditions:
            - 4 running Fedora VMs, each with 4 disk devices (1 boot from golden image DataSource + 3 blank DVs)
            - VM snapshots taken and ready to use for all 4 VMs
            - All 4 VMs stopped before restore
            - All 4 snapshot restores initiated concurrently, each with its own 5-minute deadline

        Steps:
            1. For each restore, verify it reports completion status
            2. Start the restored VMs
            3. Verify each restored VM guest disk count matches the VM spec

        Expected:
            - Each restore completed successfully within 5 minutes and each restored VM
              reports the same number of disks as the VM spec
        """
        failed_restores = [restore.name for restore in snapshot_and_restore_vms if not restore.instance.status.complete]
        assert not failed_restores, (
            f"Restores did not complete successfully within 5 minutes: {', '.join(failed_restores)}"
        )

        def verify_vm_disks(restore: VirtualMachineRestore) -> None:
            vm = VirtualMachineForTests(
                name=restore.vm_name,
                namespace=restore.namespace,
                client=restore.client,
                generate_unique_name=False,
            )
            running_vm(vm=vm)
            assert_guest_disk_count(vm=vm)

        try:
            run_parallel(
                items=snapshot_and_restore_vms,
                func=verify_vm_disks,
                label="Failed to verify restored VM disks",
                item_name=lambda r: r.vm_name,
            )
        except ExceptionGroup as disk_group:
            disk_errors = [str(error) for error in disk_group.exceptions]
            raise AssertionError(f"Restored VMs failed disk verification: {', '.join(disk_errors)}") from disk_group
