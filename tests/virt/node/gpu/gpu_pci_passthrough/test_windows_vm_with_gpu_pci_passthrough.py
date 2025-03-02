"""
GPU PCI Passthrough with Windows VM
"""

import logging
import os

import pytest
from pytest_testconfig import config as py_config

from tests.virt.node.gpu.constants import GPU_DEVICE_NAME_STR
from tests.virt.node.gpu.utils import (
    restart_and_check_gpu_exists,
    verify_gpu_device_exists_in_vm,
)
from tests.virt.utils import validate_pause_optional_migrate_unpause_windows_vm
from utilities.constants import Images
from utilities.virt import get_windows_os_dict

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.gpu,
    pytest.mark.usefixtures(
        "skip_on_psi_cluster",
        "fail_if_device_unbound_to_vfiopci_driver",
        "hco_cr_with_permitted_hostdevices",
    ),
]


LOGGER = logging.getLogger(__name__)
WIN10 = get_windows_os_dict(windows_version="win-10")
WIN10_LABELS = WIN10["template_labels"]
WIN19 = get_windows_os_dict(windows_version="win-2019")
WIN19_LABELS = WIN19["template_labels"]
DV_SIZE = Images.Windows.DEFAULT_DV_SIZE
TESTS_CLASS_NAME = "TestPCIPassthroughWinHostDevicesSpec"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vma",
    [
        pytest.param(
            {
                "dv_name": WIN10_LABELS["os"],
                "image": os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN10_IMG),
                "storage_class": py_config["default_storage_class"],
                "dv_size": DV_SIZE,
            },
            {
                "vm_name": "win10-passthrough-vm",
                "template_labels": WIN10_LABELS,
                "host_device": GPU_DEVICE_NAME_STR,
                "cloned_dv_size": DV_SIZE,
            },
            id="test_win10_pci_passthrough",
        ),
        pytest.param(
            {
                "dv_name": WIN19_LABELS["os"],
                "image": os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN2k19_IMG),
                "storage_class": py_config["default_storage_class"],
                "dv_size": DV_SIZE,
            },
            {
                "vm_name": "win19-passthrough-vm",
                "template_labels": WIN19_LABELS,
                "host_device": GPU_DEVICE_NAME_STR,
                "cloned_dv_size": DV_SIZE,
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
        validate_pause_optional_migrate_unpause_windows_vm(vm=gpu_vma)

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
        validate_pause_optional_migrate_unpause_windows_vm(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_gpus_win_vm"])
    @pytest.mark.polarion("CNV-5744")
    def test_restart_gpus_win_vm(self, gpu_vma, supported_gpu_device):
        """
        Test Windows VM with Device using gpus spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)
