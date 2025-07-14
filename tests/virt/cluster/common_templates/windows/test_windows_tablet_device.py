"""
Common templates test tablet input device.
https://github.com/kubevirt/kubevirt/pull/1987
https://libvirt.org/formatdomain.html#elementsInput
"""

import logging
import re
import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS, WINDOWS_LATEST_OS
from tests.virt.cluster.common_templates.utils import check_vm_xml_tablet_device, set_vm_tablet_device_dict
from utilities.constants import TCP_TIMEOUT_30SEC, VIRTIO
from utilities.virt import get_windows_os_dict

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.post_upgrade,
    pytest.mark.high_resource_vm,
]


LOGGER = logging.getLogger(__name__)
WINDOWS_DESKTOP_VERSION = get_windows_os_dict(windows_version="win-10")


def check_windows_vm_tablet_device(vm, driver_state):
    """Verify tablet device values in Windows VMI using driverquery"""

    windows_driver_query = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("%systemroot%\\\\system32\\\\driverquery /fo list /v"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]

    assert re.search(
        f"Module Name:(.*)HidUsb(.*)Display Name:(.*)Microsoft "
        f"HID Class Driver(.*)Description:(.*)Microsoft HID "
        f"Class Driver(.*)Driver Type:(.*)Kernel(.*)Start "
        f"Mode:(.*)Manual(.*)State:(.*){driver_state}(.*)Status:(.*)OK",
        windows_driver_query,
        re.DOTALL,
    ), "Tablet input device (Hid) is not listed in VM drivers or is not running."


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST.get("image_path"),
                "dv_size": WINDOWS_LATEST.get("dv_size"),
            },
        ),
    ],
    indirect=True,
)
class TestWindowsTabletDevice:
    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-usb-tablet-device-vm",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "usb"}),
                },
                marks=pytest.mark.polarion("CNV-2644"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_usb_tablet_device(
        self, golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        LOGGER.info("Test tablet device - USB bus.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_windows_vm_tablet_device(vm=vm, driver_state="Running")
        check_vm_xml_tablet_device(vm=vm)

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-virtio-tablet-device-vm",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "win_tablet", "type": "tablet", "bus": VIRTIO}),
                },
                marks=pytest.mark.polarion("CNV-3444"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_virtio_tablet_device(
        self, golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        """Verify that when a Windows VM is configured with virtio tablet input
        device(virtio drivers do not support tablet device), the VM is running.
        """

        LOGGER.info("Test tablet device - virtio bus.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_windows_vm_tablet_device(vm=vm, driver_state="Stopped")
        check_vm_xml_tablet_device(vm=vm)

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "windows-server-default-tablet-device",
                    "template_labels": WINDOWS_LATEST_LABELS,
                },
                marks=pytest.mark.polarion("CNV-4151"),
            ),
        ],
        indirect=True,
    )
    def test_windows_server_default_tablet_device(
        self, golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        """Verify that when a Windows Server VM is configured by default with
        tablet device
        """

        LOGGER.info("Test Windows Server tablet device - default table device.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_windows_vm_tablet_device(vm=vm, driver_state="Running")
        check_vm_xml_tablet_device(vm=vm)


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function,"
    "golden_image_vm_instance_from_template_multi_storage_scope_function,",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_DESKTOP_VERSION.get("template_labels", {}).get("os"),
                "image": WINDOWS_DESKTOP_VERSION.get("image_path"),
                "dv_size": WINDOWS_DESKTOP_VERSION.get("dv_size"),
            },
            {
                "vm_name": "windows-desktop-default-tablet-device",
                "template_labels": WINDOWS_DESKTOP_VERSION.get("template_labels"),
            },
            marks=pytest.mark.polarion("CNV-4150"),
        ),
    ],
    indirect=True,
)
def test_windows_desktop_default_tablet_device(golden_image_vm_instance_from_template_multi_storage_scope_function):
    """Verify that when a Desktop Windows VM is configured by default with
    tablet device
    """

    LOGGER.info("Test Windows Desktop tablet device - default table device.")

    vm = golden_image_vm_instance_from_template_multi_storage_scope_function
    check_windows_vm_tablet_device(vm=vm, driver_state="Running")
    check_vm_xml_tablet_device(vm=vm)
