"""
Common templates test Fedora OS support
"""

import logging

import pytest

from tests.virt.cluster.common_templates.utils import (
    check_machine_type,
    check_vm_xml_clock,
    check_vm_xml_hyperv,
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
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_pause_optional_migrate_unpause_linux_vm,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesFedora"


HYPERV_DICT = {
    "spec": {
        "template": {
            "spec": {
                "domain": {
                    "clock": {
                        "utc": {},
                        "timer": {
                            "hpet": {"present": False},
                            "pit": {"tickPolicy": "delay"},
                            "rtc": {"tickPolicy": "catchup"},
                            "hyperv": {},
                        },
                    },
                    "features": {
                        "acpi": {},
                        "apic": {},
                        "hyperv": {
                            "relaxed": {},
                            "vapic": {},
                            "synictimer": {"direct": {}},
                            "vpindex": {},
                            "synic": {},
                            "spinlocks": {"spinlocks": 8191},
                            "frequencies": {},
                            "ipi": {},
                            "reenlightenment": {},
                            "reset": {},
                            "runtime": {},
                            "tlbflush": {},
                        },
                    },
                }
            }
        }
    }
}


@pytest.mark.parametrize(
    "golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class",
    [
        ({
            "vm_dict": HYPERV_DICT,
        })
    ],
    indirect=True,
)
class TestCommonTemplatesFedora:
    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-3351")
    def test_create_vm(
        self,
        cluster_cpu_model_scope_class,
        golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class.create(wait=True)

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3345")
    def test_start_vm(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """Test CNV common templates VM initiation"""

        running_vm(vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-2651")
    def test_vm_hyperv(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        LOGGER.info("Verify VMI HyperV values.")
        check_vm_xml_hyperv(vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class)
        check_vm_xml_clock(vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class)

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3344")
    def test_vm_console(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3348")
    def test_os_version(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """Test CNV common templates OS version"""

        vm_os_version(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-9666")
    def test_efi_secureboot_enabled_by_default(
        self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    ):
        vm = golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        assert_vm_xml_efi(vm=vm)
        assert_linux_efi(vm=vm)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3347")
    def test_domain_label(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """CNV common templates 'domain' label contains vm name"""
        vm = golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        domain_label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vm_expose_ssh",
        depends=[f"{TESTS_CLASS_NAME}::start_vm"],
    )
    @pytest.mark.polarion("CNV-3349")
    def test_expose_ssh(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """CNV common templates access VM via SSH"""

        assert golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3937")
    def test_vmi_guest_agent_info(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3573")
    def test_virtctl_guest_agent_os_info(
        self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    ):
        validate_os_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3574")
    def test_virtctl_guest_agent_fs_info(
        self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    ):
        validate_fs_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-4549")
    def test_virtctl_guest_agent_user_info(
        self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    ):
        with console.Console(vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
            validate_user_info_virtctl_vs_linux_os(
                vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
            )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3668")
    def test_vm_machine_type(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        check_machine_type(vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5917")
    def test_pause_unpause_vm(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        )

    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.polarion("CNV-5842")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"],
    )
    def test_migrate_vm(
        self,
        skip_access_mode_rwo_scope_class,
        skip_if_no_common_cpu,
        golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
    ):
        """Test SSH connectivity after migration"""
        vm = golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=vm)

    @pytest.mark.polarion("CNV-5901")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(
        self,
        skip_access_mode_rwo_scope_class,
        golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        ping_process_in_fedora_os,
    ):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
            pre_pause_pid=ping_process_in_fedora_os,
        )

    @pytest.mark.polarion("CNV-6006")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(
        self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
    ):
        assert validate_virtctl_guest_agent_data_over_time(
            vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class
        ), "Guest agent stopped responding"

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3346")
    def test_vm_deletion(self, golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class):
        """Test CNV common templates VM deletion"""
        golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class.delete(wait=True)
