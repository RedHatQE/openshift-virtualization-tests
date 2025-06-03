"""
vGPU VM upgrade tests.
Tests to verify vGPU vm running before and after cluster upgrades.
"""

import pytest

from tests.upgrade_params import (
    IUO_CNV_ALERT_ORDERING_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    VIRT_NODE_ID_PREFIX,
)
from tests.virt.utils import verify_gpu_device_exists_in_vm
from utilities.virt import running_vm

pytestmark = [
    pytest.mark.upgrade_custom,
    pytest.mark.cnv_upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.special_infra,
    pytest.mark.usefixtures(
        "non_existent_mdev_bus_nodes",
        "hco_cr_with_mdev_permitted_hostdevices_scope_session",
        "vgpu_on_nodes",
    ),
    pytest.mark.gpu,
]


class TestUpgradeVGPU:
    """Pre-upgrade test"""

    @pytest.mark.polarion("CNV-11782")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{VIRT_NODE_ID_PREFIX}::test_vgpu_vm_before_upgrade")
    def test_vgpu_vm_before_upgrade(self, supported_gpu_device, rhel_vm_for_upgrade_session_scope):
        running_vm(vm=rhel_vm_for_upgrade_session_scope, wait_for_cloud_init=True)
        verify_gpu_device_exists_in_vm(vm=rhel_vm_for_upgrade_session_scope, supported_gpu_device=supported_gpu_device)

    """ Post-upgrade test """

    @pytest.mark.polarion("CNV-11783")
    @pytest.mark.order(after=IUO_CNV_ALERT_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_vgpu_vm_before_upgrade",
        ],
        scope="session",
    )
    def test_vgpu_vm_after_upgrade(self, supported_gpu_device, rhel_vm_for_upgrade_session_scope):
        running_vm(vm=rhel_vm_for_upgrade_session_scope, wait_for_cloud_init=True)
        verify_gpu_device_exists_in_vm(vm=rhel_vm_for_upgrade_session_scope, supported_gpu_device=supported_gpu_device)
