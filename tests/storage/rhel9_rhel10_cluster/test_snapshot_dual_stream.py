"""
Snapshot and restore across RHCOS 9 and RHCOS 10 worker nodes (CNV-96772)

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests


@pytest.mark.mixed_os_nodes
class TestDualStreamSnapshot:
    __test__ = False

    @pytest.mark.manual
    def test_snapshot_rhcos9_to_rhcos10(
        self,
        admin_client: DynamicClient,
        dual_stream_snapshot_vm: VirtualMachineForTests,
    ) -> None:
        """Test that a snapshot created on RHCOS 9 can be restored on RHCOS 10 without data loss.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - RHEL VM created on an RHCOS 9 node (via affinity), with test data written, VM stopped
        Steps:
            1. Change VM affinity to RHCOS 10
            2. Create snapshot (captures RHCOS 10 affinity and data state)
            3. Restore snapshot
            4. Start VM (runs on RHCOS 10 due to restored affinity)
            5. Verify VM is on RHCOS 10 node
            6. Verify original test data is preserved

        Expected:
            - VM runs on an RHCOS 10 node after restore
            - Original test data is preserved after restore
        """

    @pytest.mark.manual
    def test_snapshot_rhcos10_to_rhcos9(
        self,
        admin_client: DynamicClient,
        dual_stream_snapshot_vm: VirtualMachineForTests,
    ) -> None:
        """Test that a snapshot created on RHCOS 10 can be restored on RHCOS 9 without data loss.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - RHEL VM created on an RHCOS 10 node (via affinity), with test data written, VM stopped
        Steps:
            1. Change VM affinity to RHCOS 9
            2. Create snapshot (captures RHCOS 9 affinity and data state)
            3. Restore snapshot
            4. Start VM (runs on RHCOS 9 due to restored affinity)
            5. Verify VM is on RHCOS 9 node
            6. Verify original test data is preserved

        Expected:
            - VM runs on an RHCOS 9 node after restore
            - Original test data is preserved after restore
        """
