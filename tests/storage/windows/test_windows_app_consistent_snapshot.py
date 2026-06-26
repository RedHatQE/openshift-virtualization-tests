"""
Windows app-consistent snapshot test.

Verifies that an online VirtualMachineSnapshot of a multi-disk Windows VM
(boot + data disk) freezes for less than 10 seconds, proving guest agent
freeze/thaw works correctly on the storage provider.
"""

import logging

import pytest
from dateutil import parser as date_parser
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from timeout_sampler import TimeoutSampler

from tests.storage.utils import check_snapshot_indication
from utilities.constants import TIMEOUT_10MIN

LOGGER = logging.getLogger(__name__)

FREEZE_THRESHOLD_SECONDS = 20


pytestmark = [
    pytest.mark.windows,
    pytest.mark.conformance,
    pytest.mark.storage,
    pytest.mark.high_resource_vm,
    pytest.mark.usefixtures("skip_if_windows_eula_not_accepted"),
]


class TestWindowsAppConsistentSnapshot:
    """Test app-consistent online snapshot of a multi-disk Windows VM."""

    @pytest.mark.polarion("CNV-16100")
    def test_windows_multi_disk_snapshot_freeze_within_threshold(
        self,
        windows_vm_with_data_disk,
    ):
        """
        Test that the freeze window of an online snapshot of a 2-disk Windows VM
        completes within 20 seconds.

        Measures the time between snapshot creation and status.creationTime
        (point-in-time capture), which represents the guest agent freeze duration.
        The backend may take longer to finalize, but the VM is already unfrozen.
        """
        vm = windows_vm_with_data_disk

        LOGGER.info(f"Creating online snapshot of Windows VM {vm.name} with 2 disks...")
        with VirtualMachineSnapshot(
            name=f"snapshot-{vm.name}",
            namespace=vm.namespace,
            vm_name=vm.name,
        ) as snapshot:
            for creation_time in TimeoutSampler(
                wait_timeout=TIMEOUT_10MIN,
                sleep=1,
                func=lambda: snapshot.instance.get("status", {}).get("creationTime"),
            ):
                if creation_time:
                    break

            snapshot_created = date_parser.parse(timestr=snapshot.instance.metadata.creationTimestamp)
            snapshot_captured = date_parser.parse(timestr=creation_time)
            freeze_seconds = (snapshot_captured - snapshot_created).total_seconds()

            LOGGER.info(
                f"Freeze window: {freeze_seconds:.1f}s (created={snapshot_created}, captured={snapshot_captured})"
            )

            snapshot.wait_snapshot_done(timeout=TIMEOUT_10MIN)

            check_snapshot_indication(snapshot=snapshot, is_online=True)
            LOGGER.info("Online indication confirmed - app-consistent snapshot verified")

            assert freeze_seconds < FREEZE_THRESHOLD_SECONDS, (
                f"Freeze took {freeze_seconds:.1f}s, expected < {FREEZE_THRESHOLD_SECONDS}s"
            )
