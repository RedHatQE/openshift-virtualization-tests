"""
GPU PCI Passthrough with Windows VM
"""

import logging

import pytest

from tests.os_params import WINDOWS_10, WINDOWS_10_TEMPLATE_LABELS, WINDOWS_2019, WINDOWS_2019_TEMPLATE_LABELS
from tests.virt.node.gpu.constants import GPU_DEVICE_NAME_STR
from tests.virt.node.gpu.utils import (
    restart_and_check_gpu_exists,
)
from tests.virt.utils import validate_pause_unpause_windows_vm, verify_gpu_device_exists_in_vm
from utilities.constants import Images

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.special_infra,
    pytest.mark.high_resource_vm,
    pytest.mark.gpu,
    pytest.mark.usefixtures("fail_if_device_unbound_to_vfiopci_driver", "hco_cr_with_permitted_hostdevices"),
]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestPCIPassthroughWinHostDevicesSpec"


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, gpu_vma",
    [
        pytest.param(
            {"os_dict": WINDOWS_10},
            {
                "vm_name": "win10-passthrough-vm",
                "template_labels": WINDOWS_10_TEMPLATE_LABELS,
                "host_device": GPU_DEVICE_NAME_STR,
                "cloned_dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            id="test_win10_pci_passthrough",
        ),
        pytest.param(
            {"os_dict": WINDOWS_2019},
            {
                "vm_name": "win19-passthrough-vm",
                "template_labels": WINDOWS_2019_TEMPLATE_LABELS,
                "host_device": GPU_DEVICE_NAME_STR,
                "cloned_dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            id="test_win19_pci_passthrough",
        ),
    ],
    indirect=True,
)
class TestPCIPassthroughWinHostDevicesSpec:
    """
    Test PCI Passthrough with Windows VM using HostDevices Spec.
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_access_hostdevices_win_vm")
    @pytest.mark.polarion("CNV-5646")
    def test_access_hostdevices_win_vm(self, supported_gpu_device, gpu_vma):
        """
        Test Device is accessible in Windows VM with hostdevices spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vma, supported_gpu_device=supported_gpu_device)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_hostdevices_win_vm"])
    @pytest.mark.polarion("CNV-5647")
    def test_pause_unpause_hostdevices_win_vm(self, gpu_vma):
        """
        Test Windows VM with Device using hostdevices spec, can be paused and unpaused successfully.
        """
        validate_pause_unpause_windows_vm(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_hostdevices_win_vm"])
    @pytest.mark.polarion("CNV-5648")
    def test_restart_hostdevices_win_vm(self, gpu_vma, supported_gpu_device):
        """
        Test Windows VM with Device using hostdevices spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_access_gpus_win_vm")
    @pytest.mark.polarion("CNV-5742")
    def test_access_gpus_win_vm(self, gpu_vma, updated_vm_gpus_spec, supported_gpu_device):
        """
        Test Device is accessible in Windows VM with gpus spec.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-5743")
    def test_pause_unpause_gpus_win_vm(self, gpu_vma):
        """
        Test Windows VM with Device using gpus spec, can be paused and unpaused successfully.
        """
        validate_pause_unpause_windows_vm(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-5744")
    def test_restart_gpus_win_vm(self, gpu_vma, supported_gpu_device):
        """
        Test Windows VM with Device using gpus spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)
