from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from ocp_resources.virtual_machine_restore import VirtualMachineRestore

from tests.storage.upgrade.constants import (
    UPGRADE_FIRST_FILE_CONTENT,
    UPGRADE_FIRST_FILE_NAME,
    UPGRADE_SECOND_FILE_NAME,
)
from tests.storage.utils import assert_disk_bus
from tests.upgrade_params import (
    HOTPLUG_VM_AFTER_UPGRADE_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID,
    SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE,
    STORAGE_NODE_ID_PREFIX,
)
from utilities.constants import DEPENDENCY_SCOPE_SESSION, HOTPLUG_DISK_VIRTIO_BUS
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist,
    run_command_on_vm_and_check_output,
    wait_for_vm_volume_ready,
)
from utilities.virt import migrate_vm_and_verify, running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.datavolume import DataVolume

    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
]


@pytest.mark.usefixtures("updated_default_storage_class_ocs_virt")
class TestUpgradeStorage:
    """Pre-upgrade tests"""

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5993")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_restore_before_upgrade")
    def test_vm_snapshot_restore_before_upgrade(
        self,
        admin_client,
        skip_if_no_storage_class_for_snapshot,
        rhel_vm_for_upgrade_a,
        snapshots_for_upgrade_a,
    ):
        with VirtualMachineRestore(
            client=admin_client,
            name=f"restore-snapshot-{rhel_vm_for_upgrade_a.name}",
            namespace=snapshots_for_upgrade_a.namespace,
            vm_name=rhel_vm_for_upgrade_a.name,
            snapshot_name=snapshots_for_upgrade_a.name,
        ) as vm_restore:
            if rhel_vm_for_upgrade_a.ready:
                rhel_vm_for_upgrade_a.stop(wait=True)
            vm_restore.wait_restore_done()
            running_vm(vm=rhel_vm_for_upgrade_a)
            # Verify first file exists (created before snapshot)
            run_command_on_vm_and_check_output(
                vm=rhel_vm_for_upgrade_a,
                command=f"cat {UPGRADE_FIRST_FILE_NAME}",
                expected_result=UPGRADE_FIRST_FILE_CONTENT,
            )

            # Verify second file does NOT exist (created after snapshot)
            run_command_on_vm_and_check_output(
                vm=rhel_vm_for_upgrade_a,
                command=f"test ! -f {UPGRADE_SECOND_FILE_NAME} && echo 'file not found'",
                expected_result="file not found",
            )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5995")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_created_before_upgrade")
    def test_vm_snapshot_created_before_upgrade(
        self,
        skip_if_no_storage_class_for_snapshot,
        snapshots_for_upgrade_b,
    ):
        assert snapshots_for_upgrade_b.instance.status.readyToUse

    @pytest.mark.polarion("CNV-7258")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{STORAGE_NODE_ID_PREFIX}::test_vm_with_hotplug_before_upgrade")
    def test_vm_with_hotplug_before_upgrade(
        self,
        skip_if_config_default_storage_class_access_mode_rwo,
        enabled_feature_gate_for_declarative_hotplug_volumes_upg,
        upgrade_namespace_scope_session,
        blank_disk_dv_with_default_sc,
        fedora_vm_for_hotplug_upg,
        hotplug_volume_upg,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_upg, volume_name=blank_disk_dv_with_default_sc.name)
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_disk_bus(
            vm=fedora_vm_for_hotplug_upg,
            volume=blank_disk_dv_with_default_sc,
            expected_bus=HOTPLUG_DISK_VIRTIO_BUS,
        )
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_upg)

    """ Post-upgrade tests """

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5994")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_restore_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_snapshot_restore_check_after_upgrade(
        self,
        rhel_vm_for_upgrade_a,
    ):
        running_vm(vm=rhel_vm_for_upgrade_a)
        # Verify first file exists (created before snapshot, should still be there after upgrade)
        run_command_on_vm_and_check_output(
            vm=rhel_vm_for_upgrade_a,
            command=f"cat {UPGRADE_FIRST_FILE_NAME}",
            expected_result=UPGRADE_FIRST_FILE_CONTENT,
        )

        # Verify second file does NOT exist (was created after snapshot, should not be present after restore)
        run_command_on_vm_and_check_output(
            vm=rhel_vm_for_upgrade_a,
            command=f"test ! -f {UPGRADE_SECOND_FILE_NAME} && echo 'file not found'",
            expected_result="file not found",
        )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5996")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_created_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_snapshot_restore_create_after_upgrade(
        self, admin_client, rhel_vm_for_upgrade_b, snapshots_for_upgrade_b
    ):
        with VirtualMachineRestore(
            client=admin_client,
            name=f"restore-snapshot-{rhel_vm_for_upgrade_b.name}",
            namespace=snapshots_for_upgrade_b.namespace,
            vm_name=rhel_vm_for_upgrade_b.name,
            snapshot_name=snapshots_for_upgrade_b.name,
        ) as vm_restore:
            if rhel_vm_for_upgrade_b.ready:
                rhel_vm_for_upgrade_b.stop(wait=True)
            vm_restore.wait_restore_done()

            running_vm(vm=rhel_vm_for_upgrade_b)

            # Verify first file exists (created before snapshot)
            run_command_on_vm_and_check_output(
                vm=rhel_vm_for_upgrade_b,
                command=f"cat {UPGRADE_FIRST_FILE_NAME}",
                expected_result=UPGRADE_FIRST_FILE_CONTENT,
            )

            # Verify second file does NOT exist (created after snapshot)
            run_command_on_vm_and_check_output(
                vm=rhel_vm_for_upgrade_b,
                command=f"test ! -f {UPGRADE_SECOND_FILE_NAME} && echo 'file not found'",
                expected_result="file not found",
            )

    @pytest.mark.polarion("CNV-5310")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=HOTPLUG_VM_AFTER_UPGRADE_NODE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{STORAGE_NODE_ID_PREFIX}::test_vm_with_hotplug_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    @pytest.mark.usefixtures("hotplug_volume_upg", "fedora_vm_for_hotplug_upg_ssh_connectivity")
    def test_vm_with_hotplug_after_upgrade(
        self,
        admin_client: DynamicClient,
        blank_disk_dv_with_default_sc: DataVolume,
        fedora_vm_for_hotplug_upg: VirtualMachineForTests,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_upg, volume_name=blank_disk_dv_with_default_sc.name)
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_disk_bus(
            vm=fedora_vm_for_hotplug_upg,
            volume=blank_disk_dv_with_default_sc,
            expected_bus=HOTPLUG_DISK_VIRTIO_BUS,
        )
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_upg)
        migrate_vm_and_verify(vm=fedora_vm_for_hotplug_upg, client=admin_client, check_ssh_connectivity=True)
