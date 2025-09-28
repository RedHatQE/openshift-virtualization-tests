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

from tests.os_params import WINDOWS_10, WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from tests.virt.cluster.common_templates.utils import check_vm_xml_tablet_device, set_vm_tablet_device_dict
from utilities.constants import TCP_TIMEOUT_30SEC, VIRTIO

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.post_upgrade,
    pytest.mark.high_resource_vm,
]


LOGGER = logging.getLogger(__name__)


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
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": WINDOWS_LATEST})],
    indirect=True,
)
class TestWindowsTabletDevice:
    @pytest.mark.parametrize(
        "tablet_device_vm",
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
    def test_tablet_usb_tablet_device(self, tablet_device_vm):
        LOGGER.info("Test tablet device - USB bus.")

        check_windows_vm_tablet_device(vm=tablet_device_vm, driver_state="Running")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
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
    def test_tablet_virtio_tablet_device(self, tablet_device_vm):
        """Verify that when a Windows VM is configured with virtio tablet input
        device(virtio drivers do not support tablet device), the VM is running.
        """

        LOGGER.info("Test tablet device - virtio bus.")

        check_windows_vm_tablet_device(vm=tablet_device_vm, driver_state="Stopped")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
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
    def test_windows_server_default_tablet_device(self, tablet_device_vm):
        """Verify that when a Windows Server VM is configured by default with
        tablet device
        """

        LOGGER.info("Test Windows Server tablet device - default table device.")

        check_windows_vm_tablet_device(vm=tablet_device_vm, driver_state="Running")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
        [
            pytest.param(
                {
                    "vm_name": "windows-desktop-default-tablet-device",
                    "template_labels": WINDOWS_10.get("template_labels"),
                },
                marks=pytest.mark.polarion("CNV-4150"),
            ),
        ],
        indirect=True,
    )
    def test_windows_desktop_default_tablet_device(self, tablet_device_vm):
        """Verify that when a Desktop Windows VM is configured by default with
        tablet device
        """

        LOGGER.info("Test Windows Desktop tablet device - default table device.")

        check_windows_vm_tablet_device(vm=tablet_device_vm, driver_state="Running")
        check_vm_xml_tablet_device(vm=tablet_device_vm)
