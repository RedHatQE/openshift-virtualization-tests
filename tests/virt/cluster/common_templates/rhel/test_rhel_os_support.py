"""
Common templates test RHEL OS support
"""

import logging

import pytest

from tests.virt.cluster.common_templates.utils import (
    check_machine_type,
    validate_fs_info_virtctl_vs_linux_os,
    validate_os_info_virtctl_vs_linux_os,
    validate_user_info_virtctl_vs_linux_os,
    vm_os_version,
)
from utilities import console
from utilities.constants import LINUX_STR
from utilities.infra import validate_os_info_vmi_vs_linux_os
from utilities.virt import (
    assert_linux_efi,
    assert_vm_xml_efi,
    check_qemu_guest_agent_installed,
    check_vm_xml_smbios,
    migrate_vm_and_verify,
    running_vm,
    update_vm_efi_spec_and_restart,
    validate_libvirt_persistent_domain,
    validate_pause_unpause_linux_vm,
    validate_virtctl_guest_agent_after_guest_reboot,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesRhel"


class TestCommonTemplatesRhel:
    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-3802")
    def test_create_vm(self, matrix_rhel_os_vm_from_template):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        matrix_rhel_os_vm_from_template.create(wait=True)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3266")
    def test_start_vm(self, matrix_rhel_os_vm_from_template):
        """Test CNV common templates VM initiation"""

        running_vm(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3259")
    def test_vm_console(self, matrix_rhel_os_vm_from_template):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3318")
    def test_os_version(self, matrix_rhel_os_vm_from_template):
        """Test CNV common templates OS version"""

        vm_os_version(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-8712")
    def test_efi_secureboot_enabled_by_default(
        self, xfail_on_rhel_version_below_rhel9, matrix_rhel_os_vm_from_template
    ):
        """Test CNV common templates EFI secureboot status"""

        assert_vm_xml_efi(vm=matrix_rhel_os_vm_from_template)
        assert_linux_efi(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3306")
    def test_domain_label(self, matrix_rhel_os_vm_from_template):
        """CNV common templates 'domain' label contains vm name"""

        vm = matrix_rhel_os_vm_from_template
        label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert label == vm.name, f"Wrong domain label: {label}"

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vm_expose_ssh", depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3320")
    def test_expose_ssh(self, matrix_rhel_os_vm_from_template):
        """CNV common templates access VM via SSH"""
        assert matrix_rhel_os_vm_from_template.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vmi_guest_agent", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-6688")
    def test_vmi_guest_agent_exists(self, matrix_rhel_os_vm_from_template):
        assert check_qemu_guest_agent_installed(ssh_exec=matrix_rhel_os_vm_from_template.ssh_exec), (
            "qemu guest agent package is not installed"
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vmi_guest_agent_info", depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"]
    )
    @pytest.mark.polarion("CNV-3513")
    def test_vmi_guest_agent_info(self, matrix_rhel_os_vm_from_template):
        validate_os_info_vmi_vs_linux_os(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-4195")
    def test_virtctl_guest_agent_os_info(self, matrix_rhel_os_vm_from_template):
        validate_os_info_virtctl_vs_linux_os(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-4550")
    def test_virtctl_guest_agent_user_info(self, matrix_rhel_os_vm_from_template):
        with console.Console(vm=matrix_rhel_os_vm_from_template):
            validate_user_info_virtctl_vs_linux_os(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-6531")
    def test_virtctl_guest_agent_fs_info(self, xfail_rhel_with_old_guest_agent, matrix_rhel_os_vm_from_template):
        validate_fs_info_virtctl_vs_linux_os(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3671")
    def test_vm_machine_type(self, matrix_rhel_os_vm_from_template):
        check_machine_type(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4201")
    def test_vm_smbios_default(self, smbios_from_kubevirt_config, matrix_rhel_os_vm_from_template):
        check_vm_xml_smbios(vm=matrix_rhel_os_vm_from_template, cm_values=smbios_from_kubevirt_config)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5916")
    def test_pause_unpause_vm(self, matrix_rhel_os_vm_from_template):
        validate_pause_unpause_linux_vm(vm=matrix_rhel_os_vm_from_template)

    @pytest.mark.arm64
    @pytest.mark.smoke
    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-3038")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"]
    )
    def test_migrate_vm(self, matrix_rhel_os_vm_from_template):
        """Test SSH connectivity after migration"""
        vm = matrix_rhel_os_vm_from_template
        migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=vm)

    @pytest.mark.arm64
    @pytest.mark.polarion("CNV-5902")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(self, matrix_rhel_os_vm_from_template, ping_process_in_rhel_os):
        validate_pause_unpause_linux_vm(
            vm=matrix_rhel_os_vm_from_template,
            pre_pause_pid=ping_process_in_rhel_os(matrix_rhel_os_vm_from_template),
        )

    @pytest.mark.arm64
    @pytest.mark.polarion("CNV-6007")
    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent", f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"]
    )
    def test_verify_virtctl_guest_agent_data_after_migrate(self, matrix_rhel_os_vm_from_template):
        assert validate_virtctl_guest_agent_data_over_time(vm=matrix_rhel_os_vm_from_template), (
            "Guest agent stopped responding"
        )

    @pytest.mark.polarion("CNV-12221")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent_info"])
    def test_vmi_guest_agent_info_after_guest_reboot(self, matrix_rhel_os_vm_from_template):
        validate_virtctl_guest_agent_after_guest_reboot(vm=matrix_rhel_os_vm_from_template, os_type=LINUX_STR)

    @pytest.mark.polarion("CNV-6951")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_efi_secureboot_disabled(self, xfail_on_rhel_version_below_rhel9, matrix_rhel_os_vm_from_template):
        vm = matrix_rhel_os_vm_from_template
        update_vm_efi_spec_and_restart(vm=vm, spec={"secureBoot": False})
        assert_vm_xml_efi(vm=vm, secure_boot_enabled=False)
        assert_linux_efi(vm=vm)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3269")
    def test_vm_deletion(self, matrix_rhel_os_vm_from_template):
        """Test CNV common templates VM deletion"""
        matrix_rhel_os_vm_from_template.delete(wait=True)
