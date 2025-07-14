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
from pyhelper_utils.shell import run_ssh_commands

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from tests.virt.cluster.common_templates.utils import check_vm_xml_tablet_device, set_vm_tablet_device_dict
from utilities.constants import VIRTIO, Images
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)
# Negative tests require a DV, however its content is not important (VM will not be created).
FAILED_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
FAILED_VM_DV_SIZE = Images.Cirros.DEFAULT_DV_SIZE


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
    "golden_image_data_volume_multi_storage_scope_class,",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestRHELTabletDevice:
    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-virtio-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"bus": VIRTIO, "name": "tablet", "type": "tablet"}),
                },
                marks=pytest.mark.polarion("CNV-3072"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_virtio_tablet_device(
        self, golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        LOGGER.info("Test tablet device - virtio bus.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_vm_system_tablet_device(vm=vm, expected_device="Virtio")
        check_vm_xml_tablet_device(vm=vm)

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-usb-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "my_tablet", "type": "tablet", "bus": "usb"}),
                },
                marks=pytest.mark.polarion("CNV-3073"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_usb_tablet_device(
        self,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):
        LOGGER.info("Test tablet device -  USB bus.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_vm_system_tablet_device(vm=vm, expected_device="USB")
        check_vm_xml_tablet_device(vm=vm)

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-default-tablet-device-vm",
                    "start_vm": True,
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet"}),
                },
                marks=pytest.mark.polarion("CNV-2640"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_default_bus_tablet_device(
        self,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):
        LOGGER.info("Test tablet device - default device bus - USB.")

        vm = golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function
        check_vm_system_tablet_device(vm=vm, expected_device="USB")
        check_vm_xml_tablet_device(vm=vm)

    @pytest.mark.parametrize(
        "golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function",
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
    def test_tablet_device_migrate_vm(
        self,
        cluster_cpu_model_scope_class,
        golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
    ):
        migrate_vm_and_verify(
            vm=golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function,
            check_ssh_connectivity=True,
        )


@pytest.mark.s390x
@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": FAILED_VM_IMAGE,
                "dv_size": FAILED_VM_DV_SIZE,
            },
        ),
    ],
    indirect=True,
)
class TestRHELTabletDeviceNegative:
    @pytest.mark.parametrize(
        "golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-ps2-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "ps2"}),
                },
                marks=pytest.mark.polarion("CNV-3074"),
            ),
            pytest.param(
                {
                    "vm_name": "rhel-zen-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "tablet", "bus": "zen"}),
                },
                marks=pytest.mark.polarion("CNV-3441"),
            ),
            pytest.param(
                {
                    "vm_name": "rhel-tranition-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({
                        "name": "tablet1",
                        "type": "tablet",
                        "bus": "virtio-transitional",
                    }),
                },
                marks=pytest.mark.polarion("CNV-3442"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_invalid_usb_tablet_device(
        self, golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        LOGGER.info("Test tablet device - wrong device bus.")

        with pytest.raises(
            UnprocessibleEntityError,
            match=r".*Input device can have only virtio or usb bus.*",
        ):
            golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function.create()

    @pytest.mark.parametrize(
        "golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function",
        [
            pytest.param(
                {
                    "vm_name": "rhel-keyboard-tablet-device-vm",
                    "template_labels": RHEL_LATEST_LABELS,
                    "vm_dict": set_vm_tablet_device_dict({"name": "tablet1", "type": "keyboard", "bus": "usb"}),
                },
                marks=pytest.mark.polarion("CNV-2642"),
            ),
        ],
        indirect=True,
    )
    def test_tablet_invalid_type_tablet_device(
        self, golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function
    ):
        LOGGER.info("Test tablet device - wrong device type.")

        with pytest.raises(
            UnprocessibleEntityError,
            match=r".*Input device can have only tablet type.*",
        ):
            golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function.create()
