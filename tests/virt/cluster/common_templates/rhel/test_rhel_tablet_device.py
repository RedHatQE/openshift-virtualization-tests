"""
Common templates test tablet input device.
https://github.com/kubevirt/kubevirt/pull/1987
https://libvirt.org/formatdomain.html#elementsInput
"""

import logging
import re
import shlex

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands

from tests.os_params import FEDORA_LATEST, RHEL_LATEST, RHEL_LATEST_LABELS
from tests.virt.cluster.common_templates.utils import check_vm_xml_tablet_device, set_vm_tablet_device_dict
from utilities.constants import VIRTIO
from utilities.virt import VirtualMachineForTestsFromTemplate, migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)


def check_vm_system_tablet_device(vm, expected_device):
    """Verify tablet device parameters in VMI /sys/devices file"""
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(r"grep -rs '^QEMU *.* Tablet' /sys/devices ||true"),
    )[0]

    assert re.search(rf"/sys/devices/pci(.*)QEMU {expected_device} Tablet", output), (
        f"Wrong tablet device in VM: {output}, expected: {expected_device}"
    )


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": RHEL_LATEST})],
    indirect=True,
)
class TestRHELTabletDevice:
    @pytest.mark.parametrize(
        "tablet_device_vm",
        [
            pytest.param(
                {
                    "vm_name": "rhel-virtio-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"bus": VIRTIO, "name": "tablet", "type": "tablet"}),
                },
                marks=pytest.mark.polarion("CNV-3072"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_virtio_tablet_device(self, tablet_device_vm):
        LOGGER.info("Test tablet device - virtio bus.")

        check_vm_system_tablet_device(vm=tablet_device_vm, expected_device="Virtio")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
        [
            pytest.param(
                {
                    "vm_name": "rhel-usb-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "my_tablet", "type": "tablet", "bus": "usb"}),
                },
                marks=pytest.mark.polarion("CNV-3073"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_usb_tablet_device(self, tablet_device_vm):
        LOGGER.info("Test tablet device -  USB bus.")

        check_vm_system_tablet_device(vm=tablet_device_vm, expected_device="USB")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
        [
            pytest.param(
                {
                    "vm_name": "rhel-default-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet"}),
                },
                marks=pytest.mark.polarion("CNV-2640"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_default_bus_tablet_device(self, tablet_device_vm):
        LOGGER.info("Test tablet device - default device bus - USB.")

        check_vm_system_tablet_device(vm=tablet_device_vm, expected_device="USB")
        check_vm_xml_tablet_device(vm=tablet_device_vm)

    @pytest.mark.parametrize(
        "tablet_device_vm",
        [
            pytest.param(
                {
                    "vm_name": "rhel-migrate-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "my_tablet", "type": "tablet", "bus": "usb"}),
                    "set_vm_common_cpu": True,
                },
                marks=[pytest.mark.polarion("CNV-5833"), pytest.mark.rwx_default_storage],
            ),
        ],
        indirect=True,
    )
    def test_tablet_device_migrate_vm(self, tablet_device_vm):
        migrate_vm_and_verify(vm=tablet_device_vm, check_ssh_connectivity=True)


@pytest.mark.s390x
@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": FEDORA_LATEST})],
    indirect=True,
)
class TestRHELTabletDeviceNegative:
    @pytest.mark.parametrize(
        "vm_name, vm_dict",
        [
            pytest.param(
                "rhel-ps2-tablet-device-vm",
                set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "ps2"}),
                marks=pytest.mark.polarion("CNV-3074"),
            ),
            pytest.param(
                "rhel-zen-tablet-device-vm",
                set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "zen"}),
                marks=pytest.mark.polarion("CNV-3441"),
            ),
            pytest.param(
                "rhel-tranition-tablet-device-vm",
                set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "virtio-transitional"}),
                marks=pytest.mark.polarion("CNV-3442"),
            ),
        ],
        indirect=False,
    )
    def test_tablet_invalid_usb_tablet_device(
        self, vm_name, vm_dict, unprivileged_client, namespace, golden_image_data_source_for_test_scope_class
    ):
        LOGGER.info("Test tablet device - wrong device bus.")

        with pytest.raises(UnprocessibleEntityError, match=r".*Input device can have only virtio or usb bus.*"):
            with VirtualMachineForTestsFromTemplate(
                name=vm_name,
                namespace=namespace.name,
                client=unprivileged_client,
                data_source=golden_image_data_source_for_test_scope_class,
                labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
                vm_dict=vm_dict,
            ):
                LOGGER.error(f"VM created with invalid device bus - {vm_dict['bus']}!")

    @pytest.mark.parametrize(
        "vm_dict",
        [
            pytest.param(
                set_vm_tablet_device_dict({"name": "tablet1", "type": "keyboard", "bus": "usb"}),
                marks=pytest.mark.polarion("CNV-2642"),
            ),
        ],
        indirect=False,
    )
    def test_tablet_invalid_type_tablet_device(
        self, vm_dict, unprivileged_client, namespace, golden_image_data_source_for_test_scope_class
    ):
        LOGGER.info("Test tablet device - wrong device type.")

        with pytest.raises(UnprocessibleEntityError, match=r".*Input device can have only tablet type.*"):
            with VirtualMachineForTestsFromTemplate(
                name="rhel-keyboard-tablet-device-vm",
                namespace=namespace.name,
                client=unprivileged_client,
                data_source=golden_image_data_source_for_test_scope_class,
                labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
                vm_dict=vm_dict,
            ):
                LOGGER.error(f"VM created with invalid device type - {vm_dict['type']}!")
