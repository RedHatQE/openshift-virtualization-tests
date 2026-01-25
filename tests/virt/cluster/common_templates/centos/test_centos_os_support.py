"""
Common templates test CentOS support
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
    check_vm_xml_smbios,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_pause_unpause_linux_vm,
    validate_virtctl_guest_agent_after_guest_reboot,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesCentos"


@pytest.mark.s390x
class TestCommonTemplatesCentos:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-5337")
    def test_create_vm(self, matrix_centos_os_vm_from_template):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        matrix_centos_os_vm_from_template.create(wait=True)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5338")
    def test_start_vm(self, matrix_centos_os_vm_from_template):
        """Test CNV common templates VM initiation"""

        running_vm(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5341")
    def test_vm_console(self, matrix_centos_os_vm_from_template):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5342")
    def test_os_version(self, matrix_centos_os_vm_from_template):
        """Test CNV common templates OS version"""

        vm_os_version(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5344")
    def test_domain_label(self, matrix_centos_os_vm_from_template):
        """CNV common templates 'domain' label contains vm name"""
        vm = matrix_centos_os_vm_from_template
        domain_label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vm_expose_ssh", depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5345")
    def test_expose_ssh(self, matrix_centos_os_vm_from_template):
        """CNV common templates access VM via SSH"""

        assert matrix_centos_os_vm_from_template.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vmi_guest_agent_info", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"]
    )
    @pytest.mark.polarion("CNV-5346")
    def test_vmi_guest_agent_info(self, matrix_centos_os_vm_from_template):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_linux_os(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5347")
    def test_virtctl_guest_agent_os_info(self, matrix_centos_os_vm_from_template):
        validate_os_info_virtctl_vs_linux_os(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5348")
    def test_virtctl_guest_agent_fs_info(self, matrix_centos_os_vm_from_template):
        validate_fs_info_virtctl_vs_linux_os(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5349")
    def test_virtctl_guest_agent_user_info(self, matrix_centos_os_vm_from_template):
        with console.Console(vm=matrix_centos_os_vm_from_template):
            validate_user_info_virtctl_vs_linux_os(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5350")
    def test_vm_machine_type(self, matrix_centos_os_vm_from_template):
        check_machine_type(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5594")
    def test_vm_smbios_default(self, smbios_from_kubevirt_config, matrix_centos_os_vm_from_template):
        check_vm_xml_smbios(vm=matrix_centos_os_vm_from_template, cm_values=smbios_from_kubevirt_config)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5918")
    def test_pause_unpause_vm(self, matrix_centos_os_vm_from_template):
        validate_pause_unpause_linux_vm(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-5841")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify", depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"]
    )
    def test_migrate_vm(self, matrix_centos_os_vm_from_template):
        """Test SSH connectivity after migration"""
        migrate_vm_and_verify(vm=matrix_centos_os_vm_from_template, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=matrix_centos_os_vm_from_template)

    @pytest.mark.polarion("CNV-5904")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(self, matrix_centos_os_vm_from_template, ping_process_in_centos_os):
        validate_pause_unpause_linux_vm(vm=matrix_centos_os_vm_from_template, pre_pause_pid=ping_process_in_centos_os)

    @pytest.mark.polarion("CNV-6008")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(self, matrix_centos_os_vm_from_template):
        assert validate_virtctl_guest_agent_data_over_time(vm=matrix_centos_os_vm_from_template), (
            "Guest agent stopped responding"
        )

    @pytest.mark.polarion("CNV-12222")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent_info"])
    def test_vmi_guest_agent_info_after_guest_reboot(self, matrix_centos_os_vm_from_template):
        validate_virtctl_guest_agent_after_guest_reboot(vm=matrix_centos_os_vm_from_template, os_type=LINUX_STR)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5351")
    def test_vm_deletion(self, matrix_centos_os_vm_from_template):
        """Test CNV common templates VM deletion"""
        matrix_centos_os_vm_from_template.delete(wait=True)
