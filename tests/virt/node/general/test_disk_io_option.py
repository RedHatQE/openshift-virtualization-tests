import logging

import pytest

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
)
from utilities.constants import ROOTDISK
from utilities.virt import get_guest_os_info, vm_instance_from_template

pytestmark = pytest.mark.usefixtures("skip_test_if_no_ocs_sc")


LOGGER = logging.getLogger(__name__)
# Use OCS SC for Block disk IO logic


def check_disk_io_option_on_domain_xml(vm, expected_disk_io_option):
    LOGGER.info(f"Check disk IO option in {vm.name} domain xml")
    guest_os_info = get_guest_os_info(vmi=vm.vmi)
    driver_io = None
    if "Windows" not in guest_os_info["name"]:
        for disk_element in vm.privileged_vmi.xml_dict["domain"]["devices"]["disk"]:
            if disk_element["alias"]["@name"] == f"ua-{ROOTDISK}":
                driver_io = disk_element["driver"]["@io"]
    else:
        disk = vm.privileged_vmi.xml_dict["domain"]["devices"]["disk"]
        if disk["source"]["@dev"] == f"/dev/{ROOTDISK}":
            driver_io = disk["driver"]["@io"]
    assert driver_io == expected_disk_io_option, f"expected:{expected_disk_io_option},found: {driver_io}"


@pytest.fixture()
def disk_options_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
):
    with vm_instance_from_template(
        request=request,
        client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
    ) as vm:
        yield vm


@pytest.mark.gating
@pytest.mark.s390x
@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": RHEL_LATEST})],
    indirect=True,
)
class TestRHELIOOptions:
    @pytest.mark.parametrize(
        "disk_options_vm, expected_disk_io_option",
        [
            pytest.param(
                {
                    "vm_name": "rhel-vm-disk-io-options-threads",
                    "template_labels": RHEL_LATEST_LABELS,
                    "disk_io_option": "threads",
                },
                "threads",
                marks=pytest.mark.polarion("CNV-4567"),
            ),
            pytest.param(
                {
                    "vm_name": "rhel-vm-disk-io-options-none",
                    "template_labels": RHEL_LATEST_LABELS,
                },
                "native",
                marks=pytest.mark.polarion("CNV-4560"),
            ),
        ],
        indirect=["disk_options_vm"],
    )
    def test_vm_with_disk_io_option_rhel(
        self,
        disk_options_vm,
        expected_disk_io_option,
    ):
        check_disk_io_option_on_domain_xml(
            vm=disk_options_vm,
            expected_disk_io_option=expected_disk_io_option,
        )


@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": WINDOWS_LATEST})],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
class TestWindowsIOOptions:
    @pytest.mark.parametrize(
        "disk_options_vm, expected_disk_io_option",
        [
            pytest.param(
                {
                    "vm_name": "win-vm-disk-io-options-none",
                    "template_labels": WINDOWS_LATEST_LABELS,
                    "cpu_threads": 2,
                },
                "native",
                marks=pytest.mark.polarion("CNV-4692"),
            ),
        ],
        indirect=["disk_options_vm"],
    )
    def test_vm_with_disk_io_option_windows(
        self,
        disk_options_vm,
        expected_disk_io_option,
    ):
        check_disk_io_option_on_domain_xml(
            vm=disk_options_vm,
            expected_disk_io_option=expected_disk_io_option,
        )
