import logging

import pytest

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    RHEL_LATEST_OS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
    WINDOWS_LATEST_OS,
)
from utilities.constants import ROOTDISK, StorageClassNames
from utilities.virt import get_guest_os_info, vm_instance_from_template

pytestmark = pytest.mark.usefixtures("skip_test_if_no_ocs_sc")


LOGGER = logging.getLogger(__name__)
# Use OCS SC for Block disk IO logic
STORAGE_CLASS = StorageClassNames.CEPH_RBD_VIRTUALIZATION


def _vm_test_params(
    template_labels,
    disk_io_option=None,
    cpu_threads=None,
):
    return {
        "vm_name": f"vm-disk-io-options-{disk_io_option if disk_io_option else 'auto-driver'}",
        "cpu_threads": cpu_threads,
        "template_labels": template_labels,
        "disk_io_option": disk_io_option,
    }


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
    golden_image_data_source_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        yield vm


@pytest.mark.gating
@pytest.mark.s390x
@pytest.mark.x86_64
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
                "storage_class": STORAGE_CLASS,
            },
        ),
    ],
    indirect=True,
)
class TestRHELIOOptions:
    @pytest.mark.parametrize(
        "disk_options_vm, expected_disk_io_option",
        [
            pytest.param(
                _vm_test_params(
                    disk_io_option="threads",
                    template_labels=RHEL_LATEST_LABELS,
                ),
                "threads",
                marks=(pytest.mark.polarion("CNV-4567"),),
            ),
            pytest.param(
                _vm_test_params(
                    template_labels=RHEL_LATEST_LABELS,
                ),
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
@pytest.mark.x86_64
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST.get("image_path"),
                "dv_size": WINDOWS_LATEST.get("dv_size"),
                "storage_class": STORAGE_CLASS,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
class TestWindowsIOOptions:
    @pytest.mark.parametrize(
        "disk_options_vm, expected_disk_io_option",
        [
            pytest.param(
                _vm_test_params(template_labels=WINDOWS_LATEST_LABELS, cpu_threads=2),
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
