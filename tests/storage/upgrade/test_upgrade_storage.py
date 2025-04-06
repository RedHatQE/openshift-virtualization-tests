import logging

import pytest
from ocp_resources.virtual_machine_restore import VirtualMachineRestore

from tests.upgrade_params import (
    CDI_SCRATCH_PRESERVE_NODE_ID,
    HOTPLUG_VM_AFTER_UPGRADE_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID,
    SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE,
    STORAGE_NODE_ID_PREFIX,
)
from utilities.constants import DEPENDENCY_SCOPE_SESSION, LS_COMMAND
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist_optional_restart,
    run_command_on_cirros_vm_and_check_output,
    wait_for_vm_volume_ready,
)
from utilities.virt import migrate_vm_and_verify

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
    @pytest.mark.polarion("CNV-4880")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{STORAGE_NODE_ID_PREFIX}::test_cdiconfig_scratch_overriden_before_upgrade")
    def test_cdiconfig_scratch_overriden_before_upgrade(
        self,
        cdi_config,
        storage_class_for_updating_cdiconfig_scratch,
        override_cdiconfig_scratch_spec,
    ):
        """
        Check that the scratch StorageClass configuration should be changed before CNV upgrade
        """
        expected_sc = storage_class_for_updating_cdiconfig_scratch.instance.metadata.name
        actual_sc = cdi_config.scratch_space_storage_class_from_status
        assert actual_sc == expected_sc, (
            "The scratchSpaceStorageClass on CDIConfig config should be changed before upgrade"
        )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5993")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{STORAGE_NODE_ID_PREFIX}::test_vm_snapshot_restore_before_upgrade")
    def test_vm_snapshot_restore_before_upgrade(
        self,
        skip_if_no_storage_class_for_snapshot,
        cirros_vm_for_upgrade_a,
        snapshots_for_upgrade_a,
    ):
        with VirtualMachineRestore(
            name=f"restore-snapshot-{cirros_vm_for_upgrade_a.name}",
            namespace=snapshots_for_upgrade_a.namespace,
            vm_name=cirros_vm_for_upgrade_a.name,
            snapshot_name=snapshots_for_upgrade_a.name,
        ) as vm_restore:
            vm_restore.wait_restore_done()
            cirros_vm_for_upgrade_a.start(wait=True)
            run_command_on_cirros_vm_and_check_output(
                vm=cirros_vm_for_upgrade_a,
                command=LS_COMMAND,
                expected_result="1",
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
        upgrade_namespace_scope_session,
        blank_disk_dv_with_default_sc,
        fedora_vm_for_hotplug_upg,
        hotplug_volume_upg,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_upg)
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_hotplugvolume_nonexist_optional_restart(vm=fedora_vm_for_hotplug_upg, restart=True)

    """ Post-upgrade tests """

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2952")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=CDI_SCRATCH_PRESERVE_NODE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{STORAGE_NODE_ID_PREFIX}::test_cdiconfig_scratch_overriden_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_cdiconfig_scratch_preserved_after_upgrade(
        self,
        skip_if_not_override_cdiconfig_scratch_space,
        cdi_config,
        storage_class_for_updating_cdiconfig_scratch,
    ):
        """
        Check that the scratch StorageClass configuration should be preserved by the upgrade
        """
        expected_sc = storage_class_for_updating_cdiconfig_scratch.instance.metadata.name
        actual_sc = cdi_config.scratch_space_storage_class_from_status
        assert actual_sc == expected_sc, (
            "The scratchSpaceStorageClass on CDIConfig config should not change after upgrade"
        )

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
        cirros_vm_for_upgrade_a,
    ):
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm_for_upgrade_a,
            command=LS_COMMAND,
            expected_result="1",
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
    def test_vm_snapshot_restore_create_after_upgrade(self, cirros_vm_for_upgrade_b, snapshots_for_upgrade_b):
        with VirtualMachineRestore(
            name=f"restore-snapshot-{cirros_vm_for_upgrade_b.name}",
            namespace=snapshots_for_upgrade_b.namespace,
            vm_name=cirros_vm_for_upgrade_b.name,
            snapshot_name=snapshots_for_upgrade_b.name,
        ) as vm_restore:
            vm_restore.wait_restore_done()
            cirros_vm_for_upgrade_b.start(wait=True)
            run_command_on_cirros_vm_and_check_output(
                vm=cirros_vm_for_upgrade_b,
                command=LS_COMMAND,
                expected_result="1",
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
    def test_vm_with_hotplug_after_upgrade(
        self,
        upgrade_namespace_scope_session,
        blank_disk_dv_with_default_sc,
        fedora_vm_for_hotplug_upg,
        hotplug_volume_upg,
        fedora_vm_for_hotplug_upg_ssh_connectivity,
    ):
        assert_disk_serial(vm=fedora_vm_for_hotplug_upg)
        assert_hotplugvolume_nonexist_optional_restart(vm=fedora_vm_for_hotplug_upg)
        migrate_vm_and_verify(vm=fedora_vm_for_hotplug_upg, check_ssh_connectivity=True)
