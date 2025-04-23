import logging

import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.upgrade_params import (
    CDI_SCRATCH_PRESERVE_NODE_ID,
    HOTPLUG_VM_AFTER_UPGRADE_NODE_ID,
    IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
    IUO_CNV_ALERT_ORDERING_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID,
    SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE,
    VIRT_NODE_ID_PREFIX,
)
from tests.virt.upgrade.utils import (
    mismatching_src_pvc_names,
    verify_linux_boot_time,
    verify_run_strategy_vmi_status,
    verify_vms_ssh_connectivity,
    verify_windows_boot_time,
    vm_is_migrateable,
)
from utilities.constants import DATA_SOURCE_NAME, DEPENDENCY_SCOPE_SESSION
from utilities.exceptions import ResourceValueError
from utilities.virt import migrate_vm_and_verify, vm_console_run_commands

LOGGER = logging.getLogger(__name__)
VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID = f"{VIRT_NODE_ID_PREFIX}::test_is_vm_running_after_upgrade"

VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID = f"{VIRT_NODE_ID_PREFIX}::test_is_vm_running_before_upgrade"

MIGRATION_AFTER_UPGRADE_TEST_NODE_ID = f"{VIRT_NODE_ID_PREFIX}::test_migration_after_upgrade"

MIGRATION_BEFORE_UPGRADE_TEST_NODE_ID = f"{VIRT_NODE_ID_PREFIX}::test_migration_before_upgrade"
MIGRATION_BEFORE_UPGRADE_TEST_ORDERING = [
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    MIGRATION_BEFORE_UPGRADE_TEST_NODE_ID,
]
AFTER_UPGRADE_STORAGE_ORDERING = [
    HOTPLUG_VM_AFTER_UPGRADE_NODE_ID,
    CDI_SCRATCH_PRESERVE_NODE_ID,
    SNAPSHOT_RESTORE_CREATE_AFTER_UPGRADE,
    SNAPSHOT_RESTORE_CHECK_AFTER_UPGRADE_ID,
]

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
]


@pytest.mark.usefixtures("base_templates")
class TestUpgradeVirt:
    """Pre-upgrade tests"""

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2974")
    @pytest.mark.order("first")
    @pytest.mark.dependency(name=VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID)
    def test_is_vm_running_before_upgrade(self, vms_for_upgrade, linux_boot_time_before_upgrade):
        for vm in vms_for_upgrade:
            assert vm.vmi.status == VirtualMachineInstance.Status.RUNNING

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2987")
    @pytest.mark.order(before=MIGRATION_BEFORE_UPGRADE_TEST_ORDERING)
    @pytest.mark.dependency(
        name=f"{VIRT_NODE_ID_PREFIX}::test_vm_console_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_console_before_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(vm=vm, commands=["ls"])

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-4208")
    @pytest.mark.order(before=MIGRATION_BEFORE_UPGRADE_TEST_ORDERING)
    @pytest.mark.dependency(
        name=f"{VIRT_NODE_ID_PREFIX}::test_vm_ssh_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_ssh_before_upgrade(self, vms_for_upgrade):
        verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.ocp_upgrade
    @pytest.mark.polarion("CNV-2975")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{VIRT_NODE_ID_PREFIX}::test_migration_before_upgrade",
        depends=[VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_migration_before_upgrade(self, skip_if_no_common_cpu, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm_is_migrateable(vm=vm):
                migrate_vm_and_verify(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-6999")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID, after=MIGRATION_BEFORE_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(name=f"{VIRT_NODE_ID_PREFIX}::test_vm_run_strategy_before_upgrade")
    def test_vm_run_strategy_before_upgrade(
        self,
        manual_run_strategy_vm,
        always_run_strategy_vm,
        running_manual_run_strategy_vm,
        running_always_run_strategy_vm,
    ):
        verify_vms_ssh_connectivity(vms_list=[manual_run_strategy_vm, always_run_strategy_vm])

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.high_resource_vm
    @pytest.mark.polarion("CNV-7243")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID, after=MIGRATION_BEFORE_UPGRADE_TEST_NODE_ID)
    @pytest.mark.dependency(name=f"{VIRT_NODE_ID_PREFIX}::test_windows_vm_before_upgrade")
    def test_windows_vm_before_upgrade(
        self,
        windows_vm,
        windows_boot_time_before_upgrade,
    ):
        verify_vms_ssh_connectivity(vms_list=[windows_vm])

    """ Post-upgrade tests """

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-5932")
    @pytest.mark.order(after=IUO_CNV_ALERT_ORDERING_NODE_ID, before=AFTER_UPGRADE_STORAGE_ORDERING)
    @pytest.mark.dependency(
        name=IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vmi_pod_image_updates_after_upgrade_optin(
        self,
        unupdated_vmi_pods_names,
    ):
        """
        Check that the VMI Pods use the latest images after the upgrade
        """
        assert not unupdated_vmi_pods_names, f"The following VMI Pods were not updated: {unupdated_vmi_pods_names}"

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2978")
    @pytest.mark.order(after=[IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID], before=AFTER_UPGRADE_STORAGE_ORDERING)
    @pytest.mark.dependency(
        name=VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            VMS_RUNNING_BEFORE_UPGRADE_TEST_NODE_ID,
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_is_vm_running_after_upgrade(self, vms_for_upgrade, linux_boot_time_before_upgrade):
        for vm in vms_for_upgrade:
            vm.vmi.wait_until_running()
        verify_linux_boot_time(vm_list=vms_for_upgrade, initial_boot_time=linux_boot_time_before_upgrade)

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2980")
    @pytest.mark.order(after=[IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID], before=AFTER_UPGRADE_STORAGE_ORDERING)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_vm_console_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_console_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            vm_console_run_commands(vm=vm, commands=["ls"])

    @pytest.mark.gating
    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-4209")
    @pytest.mark.order(after=[IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID], before=AFTER_UPGRADE_STORAGE_ORDERING)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_vm_ssh_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_ssh_after_upgrade(self, vms_for_upgrade):
        verify_vms_ssh_connectivity(vms_list=vms_for_upgrade)

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-7000")
    @pytest.mark.order(
        after=[IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID, VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID],
        before=AFTER_UPGRADE_STORAGE_ORDERING,
    )
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_vm_run_strategy_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_run_strategy_after_upgrade(self, manual_run_strategy_vm, always_run_strategy_vm):
        run_strategy_vmi_list = verify_run_strategy_vmi_status(
            run_strategy_vmi_list=[manual_run_strategy_vm, always_run_strategy_vm]
        )
        verify_vms_ssh_connectivity(vms_list=run_strategy_vmi_list)

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-7244")
    @pytest.mark.order(
        after=[
            IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        ],
        before=AFTER_UPGRADE_STORAGE_ORDERING,
    )
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_windows_vm_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_windows_vm_after_upgrade(
        self,
        windows_vm,
        windows_boot_time_before_upgrade,
    ):
        verify_vms_ssh_connectivity(vms_list=[windows_vm])
        verify_windows_boot_time(windows_vm=windows_vm, initial_boot_time=windows_boot_time_before_upgrade)

    @pytest.mark.ocp_upgrade
    @pytest.mark.polarion("CNV-2979")
    @pytest.mark.order(
        after=[
            IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
            IUO_CNV_ALERT_ORDERING_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        ],
        before=AFTER_UPGRADE_STORAGE_ORDERING,
    )
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_migration_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_migration_after_upgrade(self, vms_for_upgrade):
        for vm in vms_for_upgrade:
            if vm_is_migrateable(vm=vm):
                migrate_vm_and_verify(vm=vm)
                vm_console_run_commands(vm=vm, commands=["ls"], timeout=1100)

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-3682")
    @pytest.mark.order(
        after=[
            IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
            IUO_CNV_ALERT_ORDERING_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        ],
        before=AFTER_UPGRADE_STORAGE_ORDERING,
    )
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_machine_type_after_upgrade(self, vms_for_upgrade, vms_for_upgrade_dict_before):
        for vm in vms_for_upgrade:
            assert (
                vm.instance.spec.template.spec.domain.machine.type
                == vms_for_upgrade_dict_before[vm.name]["spec"]["template"]["spec"]["domain"]["machine"]["type"]
            )

    @pytest.mark.ocp_upgrade
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5749")
    @pytest.mark.order(
        after=[
            IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
            IUO_CNV_ALERT_ORDERING_NODE_ID,
            VIRT_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID,
        ],
        before=AFTER_UPGRADE_STORAGE_ORDERING,
    )
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_golden_image_pvc_names_after_upgrade(self, base_templates, base_templates_after_upgrade):
        LOGGER.info(
            f"Comparing default value for parameter {DATA_SOURCE_NAME} in base templates before and after upgrade"
        )
        mismatching_templates = mismatching_src_pvc_names(
            pre_upgrade_templates=base_templates,
            post_upgrade_templates=base_templates_after_upgrade,
        )

        if mismatching_templates:
            raise ResourceValueError(
                f"Golden image default {DATA_SOURCE_NAME} mismatch after upgrade:\n{mismatching_templates}"
            )
