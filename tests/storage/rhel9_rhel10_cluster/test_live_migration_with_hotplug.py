"""
Live Migration with hotplugged storage between RHCOS9 and RHCOS10 worker nodes

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md
Jira: https://redhat.atlassian.net/browse/CNV-85250 # <skip-jira-utils-check>
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.storage.rhel9_rhel10_cluster.utils import HOTPLUG_TEST_FILE
from utilities.constants.cluster import RHCOS9_AFFINITY, RHCOS9_WORKER_LABEL, RHCOS10_AFFINITY
from utilities.storage import run_command_on_vm_and_check_output, wait_for_vm_volume_ready
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, set_vm_affinity

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.datavolume import DataVolume

pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.rwx_default_storage,
    pytest.mark.special_infra,
]


class TestLiveMigrationWithHotplug:
    """
    Tests for live migration with hotplugged storage volumes across RHCOS9 and RHCOS10 worker nodes.

    Markers:
        - mixed_os_nodes
        - rwx_default_storage
    """

    def test_vm_with_hotplug_migrates_from_rhcos9_to_rhcos10(
        self,
        admin_client: DynamicClient,
        vm_with_hotplug_on_rhcos9: VirtualMachineForTests,
        blank_dv_for_hotplug: DataVolume,
        written_test_data_on_rhcos9: str,
    ) -> None:
        """
        Test that a VM with a hotplugged storage volume live migrates from an RHCOS9 worker node
        to an RHCOS10 worker node without data loss or corruption.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - A dual-stream cluster has at least one RHCOS9 and one RHCOS10 worker node
            - An RWX-capable storage class is available

        Steps:
            1. Create a VM with nodeAffinity set to an RHCOS9 worker node and wait for it to be Running
            2. Create a blank PVC
            3. Hotplug the PVC to the running VM and write test data to it
            4. Live migrate the VM (VirtualMachineInstanceMigration) to an RHCOS10 worker node
            5. Verify that the VM is running on an RHCOS10 worker node
            6. Read data from the hotplugged volume on the migrated VM

        Expected:
            - Live migration completes successfully and the VM is running on an RHCOS10 worker node
            - Data on the hotplugged volume equals the test data written before migration
        """
        set_vm_affinity(vm=vm_with_hotplug_on_rhcos9, affinity=RHCOS10_AFFINITY)
        migrate_vm_and_verify(vm=vm_with_hotplug_on_rhcos9, client=admin_client, check_ssh_connectivity=True)
        wait_for_vm_volume_ready(vm=vm_with_hotplug_on_rhcos9, volume_name=blank_dv_for_hotplug.name)
        assert (
            RHCOS9_WORKER_LABEL
            not in vm_with_hotplug_on_rhcos9.vmi.get_node(privileged_client=admin_client).labels.keys()
        ), f"VM {vm_with_hotplug_on_rhcos9.name} is not running on an RHCOS10 node after migration"
        run_command_on_vm_and_check_output(
            vm=vm_with_hotplug_on_rhcos9,
            command=f"cat {HOTPLUG_TEST_FILE}",
            expected_result=written_test_data_on_rhcos9,
        )

    def test_vm_with_hotplug_migrates_from_rhcos10_to_rhcos9(
        self,
        admin_client: DynamicClient,
        vm_with_hotplug_on_rhcos10: VirtualMachineForTests,
        blank_dv_for_hotplug: DataVolume,
        written_test_data_on_rhcos10: str,
    ) -> None:
        """
        Test that a VM with a hotplugged storage volume live migrates from an RHCOS10 worker node
        to an RHCOS9 worker node without data loss or corruption.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/storage.md

        Preconditions:
            - A dual-stream cluster has at least one RHCOS9 and one RHCOS10 worker node
            - An RWX-capable storage class is available

        Steps:
            1. Create a VM with nodeAffinity set to an RHCOS10 worker node and wait for it to be Running
            2. Create a blank PVC
            3. Hotplug the PVC to the running VM and write test data to it
            4. Live migrate the VM (VirtualMachineInstanceMigration) to an RHCOS9 worker node
            5. Verify that the VM is running on an RHCOS9 worker node
            6. Read data from the hotplugged volume on the migrated VM

        Expected:
            - Live migration completes successfully and the VM is running on an RHCOS9 worker node
            - Data on the hotplugged volume equals the test data written before migration
        """
        set_vm_affinity(vm=vm_with_hotplug_on_rhcos10, affinity=RHCOS9_AFFINITY)
        migrate_vm_and_verify(vm=vm_with_hotplug_on_rhcos10, client=admin_client, check_ssh_connectivity=True)
        wait_for_vm_volume_ready(vm=vm_with_hotplug_on_rhcos10, volume_name=blank_dv_for_hotplug.name)
        assert (
            RHCOS9_WORKER_LABEL in vm_with_hotplug_on_rhcos10.vmi.get_node(privileged_client=admin_client).labels.keys()
        ), f"VM {vm_with_hotplug_on_rhcos10.name} is not running on an RHCOS9 node after migration"
        run_command_on_vm_and_check_output(
            vm=vm_with_hotplug_on_rhcos10,
            command=f"cat {HOTPLUG_TEST_FILE}",
            expected_result=written_test_data_on_rhcos10,
        )
