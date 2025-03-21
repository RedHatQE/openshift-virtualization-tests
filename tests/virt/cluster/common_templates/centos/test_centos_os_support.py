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
from utilities.infra import validate_os_info_vmi_vs_linux_os
from utilities.virt import (
    check_vm_xml_smbios,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_pause_optional_migrate_unpause_linux_vm,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesCentos"


class TestCommonTemplatesCentos:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    @pytest.mark.polarion("CNV-5337")
    def test_create_vm(
        self,
        cluster_cpu_model_scope_class,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """Test CNV VM creation from template"""

        LOGGER.info("Create VM from template.")
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.create(wait=True)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5338")
    def test_start_vm(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """Test CNV common templates VM initiation"""

        running_vm(vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5341")
    def test_vm_console(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """Test CNV common templates VM console"""

        LOGGER.info("Verify VM console connection.")
        wait_for_console(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5342")
    def test_os_version(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """Test CNV common templates OS version"""

        vm_os_version(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5344")
    def test_domain_label(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """CNV common templates 'domain' label contains vm name"""
        vm = golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        domain_label = vm.instance.spec.template.metadata["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vm_expose_ssh",
        depends=[f"{TESTS_CLASS_NAME}::start_vm"],
    )
    @pytest.mark.polarion("CNV-5345")
    def test_expose_ssh(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """CNV common templates access VM via SSH"""

        assert golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.ssh_exec.executor().is_connective(  # noqa: E501
            tcp_timeout=120
        ), "Failed to login via SSH"

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5346")
    def test_vmi_guest_agent_info(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """Test Guest OS agent info."""
        validate_os_info_vmi_vs_linux_os(vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5347")
    def test_virtctl_guest_agent_os_info(
        self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
    ):
        validate_os_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5348")
    def test_virtctl_guest_agent_fs_info(
        self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
    ):
        validate_fs_info_virtctl_vs_linux_os(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"])
    @pytest.mark.polarion("CNV-5349")
    def test_virtctl_guest_agent_user_info(
        self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
    ):
        with console.Console(vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
            validate_user_info_virtctl_vs_linux_os(
                vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
            )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5350")
    def test_vm_machine_type(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        check_machine_type(vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5594")
    def test_vm_smbios_default(
        self,
        smbios_from_kubevirt_config,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        check_vm_xml_smbios(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            cm_values=smbios_from_kubevirt_config,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    @pytest.mark.polarion("CNV-5918")
    def test_pause_unpause_vm(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        )

    @pytest.mark.polarion("CNV-5841")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        depends=[f"{TESTS_CLASS_NAME}::vm_expose_ssh"],
    )
    def test_migrate_vm(
        self,
        skip_access_mode_rwo_scope_class,
        skip_if_no_common_cpu,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
    ):
        """Test SSH connectivity after migration"""
        migrate_vm_and_verify(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            check_ssh_connectivity=True,
        )
        validate_libvirt_persistent_domain(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        )

    @pytest.mark.polarion("CNV-5904")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(
        self,
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        ping_process_in_centos_os,
    ):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
            pre_pause_pid=ping_process_in_centos_os,
        )

    @pytest.mark.polarion("CNV-6008")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(
        self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
    ):
        assert validate_virtctl_guest_agent_data_over_time(
            vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class
        ), "Guest agent stopped responding"

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    @pytest.mark.polarion("CNV-5351")
    def test_vm_deletion(self, golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class):
        """Test CNV common templates VM deletion"""
        golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class.delete(wait=True)
