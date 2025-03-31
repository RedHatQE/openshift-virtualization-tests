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


class TestCommonTemplatesWindows:
    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-2196")
    def test_create_vm(
        self,
        cluster_modern_cpu_model_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.create(wait=True)

    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3785")
    def test_start_vm(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        """Test CNV common templates VM initiation"""

        running_vm(vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-8854")
    def test_efi_secureboot_enabled_by_default(
        self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
    ):
        """Test CNV common templates EFI secureboot status"""

        vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        assert_vm_xml_efi(vm=vm)
        assert_windows_efi(vm=vm)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3512")
    def test_vmi_guest_agent_info(
        self,
        xfail_guest_agent_info_on_win2025,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4196")
    def test_virtctl_guest_agent_os_info(
        self,
        xfail_guest_agent_info_on_win2025,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        validate_os_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4197")
    def test_virtctl_guest_agent_fs_info(
        self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
    ):
        validate_fs_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4552")
    def test_virtctl_guest_agent_user_info(
        self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
    ):
        validate_user_info_virtctl_vs_windows_os(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3303")
    def test_domain_label(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        """CNV common templates 'domain' label contains vm name"""
        vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        domain_label = vm.body["spec"]["template"]["metadata"]["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-2776")
    def test_hyperv(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        LOGGER.info("Verify VM HyperV values.")

        vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        check_vm_xml_hyperv(vm=vm)
        check_windows_vm_hvinfo(vm=vm)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3674")
    def test_vm_machine_type(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        check_machine_type(vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3087")
    def test_pause_unpause_vm(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        """Test VM pause and unpause"""
        validate_pause_optional_migrate_unpause_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4203")
    def test_vm_smbios_default(
        self,
        smbios_from_kubevirt_config,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config,
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        depends=[f"{TESTS_CLASS_NAME}::start_vm"],
    )
    @pytest.mark.polarion("CNV-3335")
    def test_migrate_vm(
        self,
        skip_if_no_common_modern_cpu,
        skip_access_mode_rwo_scope_class,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
    ):
        """Test SSH connectivity after migration"""
        vm = golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=vm)

    @pytest.mark.polarion("CNV-5903")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(
        self,
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        regedit_process_in_windows_os,
    ):
        validate_pause_optional_migrate_unpause_windows_vm(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
            pre_pause_pid=regedit_process_in_windows_os,
        )

    @pytest.mark.polarion("CNV-6009")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(
        self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
    ):
        assert validate_virtctl_guest_agent_data_over_time(
            vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class
        ), "Guest agent stopped responding"

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3289")
    def test_vm_deletion(self, golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class):
        """Test CNV common templates VM deletion"""
        golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class.delete(wait=True)
