"""
Common templates test Fedora OS support
"""

import logging

import pytest

from tests.virt.cluster.common_templates.utils import (
    check_machine_type,
    check_vm_xml_clock,
    validate_fs_info_virtctl_vs_linux_os,
    validate_os_info_virtctl_vs_linux_os,
    validate_user_info_virtctl_vs_linux_os,
    vm_os_version,
)
from utilities import console
from utilities.constants import LINUX_STR
from utilities.guest_support import check_vm_xml_hyperv
from utilities.infra import validate_os_info_vmi_vs_linux_os
from utilities.virt import (
    assert_linux_efi,
    assert_vm_xml_efi,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_pause_unpause_linux_vm,
    validate_virtctl_guest_agent_after_guest_reboot,
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
    "matrix_fedora_os_vm_from_template",
    [({"vm_dict": HYPERV_DICT})],
    indirect=True,
)
class TestCommonTemplatesFedora:
    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-3351")
    def test_create_vm(self, matrix_fedora_os_vm_from_template):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        matrix_fedora_os_vm_from_template.create(wait=True)

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3345")
    def test_start_vm(self, matrix_fedora_os_vm_from_template):
        """Test CNV common templates VM initiation"""

        running_vm(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-2651")
    def test_vm_hyperv(self, matrix_fedora_os_vm_from_template):
        LOGGER.info("Verify VMI HyperV values.")
        check_vm_xml_hyperv(vm=matrix_fedora_os_vm_from_template)
        check_vm_xml_clock(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3344")
    def test_vm_console(self, matrix_fedora_os_vm_from_template):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3348")
    def test_os_version(self, matrix_fedora_os_vm_from_template):
        """Test CNV common templates OS version"""

        vm_os_version(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-9666")
    def test_efi_secureboot_enabled_by_default(self, matrix_fedora_os_vm_from_template):
        assert_vm_xml_efi(vm=matrix_fedora_os_vm_from_template)
        assert_linux_efi(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3347")
    def test_domain_label(self, matrix_fedora_os_vm_from_template):
        """CNV common templates 'domain' label contains vm name"""
        vm = matrix_fedora_os_vm_from_template
        domain_label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vm_expose_ssh", depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3349")
    def test_expose_ssh(self, matrix_fedora_os_vm_from_template):
        """CNV common templates access VM via SSH"""

        assert matrix_fedora_os_vm_from_template.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.sno
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vmi_guest_agent_info", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"]
    )
    @pytest.mark.polarion("CNV-3937")
    def test_vmi_guest_agent_info(self, matrix_fedora_os_vm_from_template):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_linux_os(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3573")
    def test_virtctl_guest_agent_os_info(self, matrix_fedora_os_vm_from_template):
        validate_os_info_virtctl_vs_linux_os(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-3574")
    @pytest.mark.jira("CNV-76696", run=False)
    def test_virtctl_guest_agent_fs_info(self, matrix_fedora_os_vm_from_template):
        validate_fs_info_virtctl_vs_linux_os(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-4549")
    def test_virtctl_guest_agent_user_info(self, matrix_fedora_os_vm_from_template):
        with console.Console(vm=matrix_fedora_os_vm_from_template):
            validate_user_info_virtctl_vs_linux_os(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-3668")
    def test_vm_machine_type(self, matrix_fedora_os_vm_from_template):
        check_machine_type(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5917")
    def test_pause_unpause_vm(self, matrix_fedora_os_vm_from_template):
        validate_pause_unpause_linux_vm(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.rwx_default_storage
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.polarion("CNV-5842")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"]
    )
    def test_migrate_vm(self, matrix_fedora_os_vm_from_template):
        """Test SSH connectivity after migration"""
        migrate_vm_and_verify(vm=matrix_fedora_os_vm_from_template, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=matrix_fedora_os_vm_from_template)

    @pytest.mark.polarion("CNV-5901")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(self, matrix_fedora_os_vm_from_template, ping_process_in_fedora_os):
        validate_pause_unpause_linux_vm(vm=matrix_fedora_os_vm_from_template, pre_pause_pid=ping_process_in_fedora_os)

    @pytest.mark.polarion("CNV-6006")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(self, matrix_fedora_os_vm_from_template):
        assert validate_virtctl_guest_agent_data_over_time(vm=matrix_fedora_os_vm_from_template), (
            "Guest agent stopped responding"
        )

    @pytest.mark.polarion("CNV-12219")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent_info"])
    def test_vmi_guest_agent_info_after_guest_reboot(self, matrix_fedora_os_vm_from_template):
        validate_virtctl_guest_agent_after_guest_reboot(vm=matrix_fedora_os_vm_from_template, os_type=LINUX_STR)

    @pytest.mark.sno
    @pytest.mark.ibm_bare_metal
    @pytest.mark.ocp_interop
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-3346")
    def test_vm_deletion(self, matrix_fedora_os_vm_from_template):
        """Test CNV common templates VM deletion"""
        matrix_fedora_os_vm_from_template.delete(wait=True)
