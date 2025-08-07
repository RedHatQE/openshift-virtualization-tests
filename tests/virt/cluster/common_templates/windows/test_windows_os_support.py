"""
Common templates test Windows OS support
"""

import logging

import pytest

from tests.virt.cluster.common_templates.utils import (
    assert_windows_efi,
    check_machine_type,
    check_vm_xml_hyperv,
    check_windows_vm_hvinfo,
    validate_fs_info_virtctl_vs_windows_os,
    validate_os_info_virtctl_vs_windows_os,
    validate_user_info_virtctl_vs_windows_os,
)
from tests.virt.utils import validate_pause_optional_migrate_unpause_windows_vm
from utilities.ssp import validate_os_info_vmi_vs_windows_os
from utilities.virt import (
    assert_vm_xml_efi,
    check_vm_xml_smbios,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_virtctl_guest_agent_data_over_time,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.special_infra, pytest.mark.high_resource_vm]

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesWindows"


@pytest.mark.usefixtures("cluster_cpu_model_scope_class")
class TestCommonTemplatesWindows:
    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-2196")
    def test_create_vm(self, matrix_windows_os_vm_from_template):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        matrix_windows_os_vm_from_template.create(wait=True)

    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.usefixtures("xfail_guest_agent_on_win2016")
    @pytest.mark.polarion("CNV-3785")
    def test_start_vm(self, matrix_windows_os_vm_from_template):
        """Test CNV common templates VM initiation"""

        running_vm(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-8854")
    def test_efi_secureboot_enabled_by_default(self, matrix_windows_os_vm_from_template):
        """Test CNV common templates EFI secureboot status"""

        assert_vm_xml_efi(vm=matrix_windows_os_vm_from_template)
        assert_windows_efi(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3512")
    def test_vmi_guest_agent_info(self, matrix_windows_os_vm_from_template):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_windows_os(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4196")
    def test_virtctl_guest_agent_os_info(self, matrix_windows_os_vm_from_template):
        validate_os_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4197")
    def test_virtctl_guest_agent_fs_info(self, matrix_windows_os_vm_from_template):
        validate_fs_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4552")
    def test_virtctl_guest_agent_user_info(self, matrix_windows_os_vm_from_template):
        validate_user_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3303")
    def test_domain_label(self, matrix_windows_os_vm_from_template):
        """CNV common templates 'domain' label contains vm name"""
        vm = matrix_windows_os_vm_from_template
        domain_label = vm.body["spec"]["template"]["metadata"]["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-2776")
    def test_hyperv(self, matrix_windows_os_vm_from_template):
        LOGGER.info("Verify VM HyperV values.")
        check_vm_xml_hyperv(vm=matrix_windows_os_vm_from_template)
        check_windows_vm_hvinfo(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3674")
    def test_vm_machine_type(self, matrix_windows_os_vm_from_template):
        check_machine_type(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3087")
    def test_pause_unpause_vm(self, matrix_windows_os_vm_from_template):
        """Test VM pause and unpause"""
        validate_pause_optional_migrate_unpause_windows_vm(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4203")
    def test_vm_smbios_default(self, smbios_from_kubevirt_config, matrix_windows_os_vm_from_template):
        check_vm_xml_smbios(vm=matrix_windows_os_vm_from_template, cm_values=smbios_from_kubevirt_config)

    @pytest.mark.rwx_default_storage
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify", depends=[f"{TESTS_CLASS_NAME}::start_vm"]
    )
    @pytest.mark.polarion("CNV-3335")
    def test_migrate_vm(self, matrix_windows_os_vm_from_template):
        """Test SSH connectivity after migration"""
        migrate_vm_and_verify(vm=matrix_windows_os_vm_from_template, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.polarion("CNV-5903")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(self, matrix_windows_os_vm_from_template, regedit_process_in_windows_os):
        validate_pause_optional_migrate_unpause_windows_vm(
            vm=matrix_windows_os_vm_from_template, pre_pause_pid=regedit_process_in_windows_os
        )

    @pytest.mark.polarion("CNV-6009")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(self, matrix_windows_os_vm_from_template):
        assert validate_virtctl_guest_agent_data_over_time(vm=matrix_windows_os_vm_from_template), (
            "Guest agent stopped responding"
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(self, matrix_windows_os_vm_from_template):
        """Test CNV common templates VM deletion"""
        matrix_windows_os_vm_from_template.delete(wait=True)
