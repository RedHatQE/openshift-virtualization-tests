"""
Snapshot and restore across RHCOS 9 and RHCOS 10 worker nodes (CNV-96772)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from tests.storage.rhel9_rhel10_cluster.snapshot_utils import verify_snapshot_restore_across_rhcos
from utilities.constants.cluster import (
    RHCOS9_AFFINITY,
    RHCOS9_VERSION,
    RHCOS10_AFFINITY,
    RHCOS10_VERSION,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTestsFromTemplate


pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.special_infra,
]


class TestDualStreamSnapshot:
    pytestmark = pytest.mark.usefixtures("skip_if_no_storage_class_for_snapshot")

    @pytest.mark.parametrize(
        argnames="golden_image_data_source_for_dual_stream_scope_function, dual_stream_snapshot_vm",
        argvalues=[
            (
                {"os_dict": RHEL_LATEST},
                {
                    "vm_name": "snap-rhcos9-restore-rhcos10-rhel",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_affinity": RHCOS9_AFFINITY,
                    "source_rhcos_version": RHCOS9_VERSION,
                    "vm_dict": {"spec": {"runStrategy": "Manual"}},
                    "start_vm": False,
                },
            ),
        ],
        ids=["RHEL-on-RHCOS9"],
        indirect=True,
    )
    def test_snapshot_rhcos9_to_rhcos10(
        self,
        admin_client: DynamicClient,
        dual_stream_snapshot_vm: VirtualMachineForTestsFromTemplate,
    ) -> None:
        """
        Test that snapshot created on RHCOS 9 can be restored on RHCOS 10 without data loss.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - RHEL VM created with affinity to RHCOS 9 worker node (runStrategy: Manual)

        Steps:
            1. Write test data to VM on RHCOS 9
            2. Stop VM
            3. Change VM affinity to RHCOS 10
            4. Create snapshot of VM (snapshot captures RHCOS 10 affinity)
            5. Restore VM from snapshot (restores to snapshot state with RHCOS 10 affinity)
            6. Start VM (runs on RHCOS 10 due to restored affinity)
            7. Verify VM is running on RHCOS 10 node
            8. Verify original test data is present after restore

        Expected:
            - Restored VM has RHCOS 10 affinity (from snapshot)
            - VM automatically runs on RHCOS 10 after start
            - Original test data is present after restore
        """
        verify_snapshot_restore_across_rhcos(
            admin_client=admin_client,
            vm=dual_stream_snapshot_vm,
            target_affinity=RHCOS10_AFFINITY,
            target_rhcos_version=RHCOS10_VERSION,
        )

    @pytest.mark.parametrize(
        argnames="golden_image_data_source_for_dual_stream_scope_function, dual_stream_snapshot_vm",
        argvalues=[
            (
                {"os_dict": RHEL_LATEST},
                {
                    "vm_name": "snap-rhcos10-restore-rhcos9-rhel",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_affinity": RHCOS10_AFFINITY,
                    "source_rhcos_version": RHCOS10_VERSION,
                    "vm_dict": {"spec": {"runStrategy": "Manual"}},
                    "start_vm": False,
                },
            ),
        ],
        ids=["RHEL-on-RHCOS10"],
        indirect=True,
    )
    def test_snapshot_rhcos10_to_rhcos9(
        self,
        admin_client: DynamicClient,
        dual_stream_snapshot_vm: VirtualMachineForTestsFromTemplate,
    ) -> None:
        """
        Test that snapshot created on RHCOS 10 can be restored on RHCOS 9 without data loss.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - RHEL VM created with affinity to RHCOS 10 worker node (runStrategy: Manual)

        Steps:
            1. Write test data to VM on RHCOS 10
            2. Stop VM
            3. Change VM affinity to RHCOS 9
            4. Create snapshot of VM (snapshot captures RHCOS 9 affinity)
            5. Restore VM from snapshot (restores to snapshot state with RHCOS 9 affinity)
            6. Start VM (runs on RHCOS 9 due to restored affinity)
            7. Verify VM is running on RHCOS 9 node
            8. Verify original test data is present after restore

        Expected:
            - Restored VM has RHCOS 9 affinity (from snapshot)
            - VM automatically runs on RHCOS 9 after start
            - Original test data is present after restore
        """
        verify_snapshot_restore_across_rhcos(
            admin_client=admin_client,
            vm=dual_stream_snapshot_vm,
            target_affinity=RHCOS9_AFFINITY,
            target_rhcos_version=RHCOS9_VERSION,
        )
