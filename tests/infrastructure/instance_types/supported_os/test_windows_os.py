import logging

import pytest

from utilities.guest_support import assert_windows_efi, check_vm_xml_hyperv, check_windows_vm_hvinfo
from utilities.virt import running_vm

pytestmark = [pytest.mark.high_resource_vm, pytest.mark.tier3]

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonPreferenceWindows"


class TestCommonPreferenceWindows:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-12269")
    def test_create_vm(
        self,
        golden_image_windows_vm,
    ):
        LOGGER.info("Create VM from preference.")
        golden_image_windows_vm.create(wait=True)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-12270")
    def test_start_vm(self, golden_image_windows_vm):
        running_vm(vm=golden_image_windows_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-12387")
    def test_efi_secureboot_enabled(self, golden_image_windows_vm):
        assert_windows_efi(vm=golden_image_windows_vm)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-12388")
    def test_hyperv(self, golden_image_windows_vm):
        check_vm_xml_hyperv(vm=golden_image_windows_vm)
        check_windows_vm_hvinfo(vm=golden_image_windows_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-12271")
    def test_vm_deletion(self, golden_image_windows_vm):
        golden_image_windows_vm.delete(wait=True)
