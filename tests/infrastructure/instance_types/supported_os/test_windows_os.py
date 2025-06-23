import logging

import pytest

from utilities.virt import (
    running_vm,
)

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonPreferenceWindows"


class TestCommonPreferenceWindows:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-0")
    def test_create_vm(
        self,
        golden_image_windows_vm,
    ):
        LOGGER.info("Create VM from preference.")
        golden_image_windows_vm.create(wait=True)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-1")
    def test_start_vm(self, golden_image_windows_vm):
        running_vm(vm=golden_image_windows_vm)

    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-2")
    # def test_efi_secureboot_enabled_by_default(self, golden_image_windows_vm):
    #     vm = golden_image_windows_vm
    #     assert_vm_xml_efi(vm=vm)
    #     assert_windows_efi(vm=vm)
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-2")
    # def test_vmi_guest_agent_info(
    #     self,
    #     golden_image_windows_vm,
    # ):
    #     validate_os_info_vmi_vs_windows_os(
    #         vm=golden_image_windows_vm,
    #     )
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-3")
    # def test_virtctl_guest_agent_os_info(
    #     self,
    #     golden_image_windows_vm,
    # ):
    #     validate_os_info_virtctl_vs_windows_os(
    #         vm=golden_image_windows_vm,
    #     )
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-4")
    # def test_virtctl_guest_agent_fs_info(self, golden_image_windows_vm):
    #     validate_fs_info_virtctl_vs_windows_os(
    #         vm=golden_image_windows_vm,
    #     )
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-5")
    # def test_virtctl_guest_agent_user_info(self, golden_image_windows_vm):
    #     validate_user_info_virtctl_vs_windows_os(
    #         vm=golden_image_windows_vm,
    #     )
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    # @pytest.mark.polarion("CNV-6")
    # def test_domain_label(self, golden_image_windows_vm):
    #     vm = golden_image_windows_vm
    #     domain_label = vm.body["spec"]["template"]["metadata"]["labels"]["kubevirt.io/domain"]
    #     assert domain_label == vm.name, f"Wrong domain label: {domain_label}"
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-7")
    # def test_hyperv(self, golden_image_windows_vm):
    #     vm = golden_image_windows_vm
    #     check_vm_xml_hyperv(vm=vm)
    #     check_windows_vm_hvinfo(vm=vm)
    #
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    # @pytest.mark.polarion("CNV-9")
    # def test_pause_unpause_vm(self, golden_image_windows_vm):
    #     validate_pause_optional_migrate_unpause_windows_vm(vm=golden_image_windows_vm)
    #
    # @pytest.mark.rwx_default_storage
    # @pytest.mark.dependency(
    #     name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
    #     depends=[f"{TESTS_CLASS_NAME}::start_vm"],
    # )
    # @pytest.mark.polarion("CNV-11")
    # def test_migrate_vm(self, golden_image_windows_vm):
    #     vm = golden_image_windows_vm
    #     migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
    #     validate_libvirt_persistent_domain(vm=vm)
    #
    # @pytest.mark.polarion("CNV-12")
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    # def test_pause_unpause_after_migrate(
    #     self,
    #     golden_image_windows_vm,
    #     regedit_process_in_windows_os,
    # ):
    #     validate_pause_optional_migrate_unpause_windows_vm(
    #         vm=golden_image_windows_vm,
    #         pre_pause_pid=regedit_process_in_windows_os,
    #     )
    #
    # @pytest.mark.polarion("CNV-13")
    # @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    # def test_verify_virtctl_guest_agent_data_after_migrate(self, golden_image_windows_vm):
    #     assert validate_virtctl_guest_agent_data_over_time(vm=golden_image_windows_vm), "Guest agent stopped responding"

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-14")
    def test_vm_deletion(self, golden_image_windows_vm):
        golden_image_windows_vm.delete(wait=True)
