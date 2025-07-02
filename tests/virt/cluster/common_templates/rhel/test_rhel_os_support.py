"""
Common templates test RHEL OS support
"""

import logging

import pytest

from tests.virt.cluster.common_templates.utils import (
    check_machine_type,
    restart_qemu_guest_agent_service,
    validate_fs_info_virtctl_vs_linux_os,
    validate_os_info_virtctl_vs_linux_os,
    validate_user_info_virtctl_vs_linux_os,
    vm_os_version,
)
from utilities import console
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
    validate_pause_optional_migrate_unpause_linux_vm,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesRhel"


class TestCommonTemplatesRhel:
    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-3802")
    def test_create_vm(
        self,
        cluster_cpu_model_scope_module,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.create(wait=True)

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3266")
    def test_start_vm(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """Test CNV common templates VM initiation"""

        running_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3259")
    def test_vm_console(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3318")
    def test_os_version(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """Test CNV common templates OS version"""

        vm_os_version(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-8712")
    def test_efi_secureboot_enabled_by_default(
        self,
        xfail_on_rhel_version_below_rhel9,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        """Test CNV common templates EFI secureboot status"""

        vm = golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        assert_vm_xml_efi(vm=vm)
        assert_linux_efi(vm=vm)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3306")
    def test_domain_label(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """CNV common templates 'domain' label contains vm name"""

        vm = golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert label == vm.name, f"Wrong domain label: {label}"

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vm_expose_ssh",
        depends=[f"{TESTS_CLASS_NAME}::start_vm"],
    )
    @pytest.mark.polarion("CNV-3320")
    def test_expose_ssh(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """CNV common templates access VM via SSH"""
        assert golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vmi_guest_agent",
        depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"],
    )
    @pytest.mark.polarion("CNV-6688")
    def test_vmi_guest_agent_exists(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        assert check_qemu_guest_agent_installed(
            ssh_exec=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.ssh_exec
        ), "qemu guest agent package is not installed"

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-3513")
    def test_vmi_guest_agent_info(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        validate_os_info_vmi_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-4195")
    def test_virtctl_guest_agent_os_info(
        self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class, rhel_os_matrix__class__
    ):
        current_rhel_name = [*rhel_os_matrix__class__][0]
        # QGA Service restart is needed because of bugs 1910326 and 1845127
        # when test rhel7, we need to restart QGA to synchronize hostname to the kernel
        if "rhel-7" in current_rhel_name:
            restart_qemu_guest_agent_service(
                vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            )
        validate_os_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-4550")
    def test_virtctl_guest_agent_user_info(
        self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
    ):
        with console.Console(vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
            validate_user_info_virtctl_vs_linux_os(
                vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
            )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent"])
    @pytest.mark.polarion("CNV-6531")
    def test_virtctl_guest_agent_fs_info(
        self,
        xfail_rhel_with_old_guest_agent,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        validate_fs_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3671")
    def test_vm_machine_type(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        check_machine_type(vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class)

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-4201")
    def test_vm_smbios_default(
        self,
        smbios_from_kubevirt_config,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config,
        )

    @pytest.mark.arm64
    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5916")
    def test_pause_unpause_vm(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        )

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.smoke
    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-3038")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"],
    )
    def test_migrate_vm(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """Test SSH connectivity after migration"""
        vm = golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=vm)

    @pytest.mark.arm64
    @pytest.mark.polarion("CNV-5902")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(
        self,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        ping_process_in_rhel_os,
    ):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
            pre_pause_pid=ping_process_in_rhel_os(
                golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
            ),
        )

    @pytest.mark.arm64
    @pytest.mark.polarion("CNV-6007")
    @pytest.mark.dependency(
        depends=[
            f"{TESTS_CLASS_NAME}::vmi_guest_agent",
            f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        ]
    )
    def test_verify_virtctl_guest_agent_data_after_migrate(
        self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
    ):
        assert validate_virtctl_guest_agent_data_over_time(
            vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        ), "Guest agent stopped responding"

    @pytest.mark.polarion("CNV-6951")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_efi_secureboot_disabled(
        self,
        xfail_on_rhel_version_below_rhel9,
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
    ):
        vm = golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class
        update_vm_efi_spec_and_restart(vm=vm, spec={"secureBoot": False})
        assert_vm_xml_efi(vm=vm, secure_boot_enabled=False)
        assert_linux_efi(vm=vm)

    @pytest.mark.arm64
    @pytest.mark.s390x
    @pytest.mark.sno
    @pytest.mark.smoke
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3269")
    def test_vm_deletion(self, golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class):
        """Test CNV common templates VM deletion"""
        golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class.delete(wait=True)
