"""
Common templates test Windows OS support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from tests.virt.cluster.common_templates.utils import (
    check_machine_type,
    validate_fs_info_virtctl_vs_windows_os,
    validate_os_info_virtctl_vs_windows_os,
    validate_user_info_virtctl_vs_windows_os,
)
from utilities.constants.images import OS_FLAVOR_WINDOWS
from utilities.constants.pytest import QUARANTINED
from utilities.guest_support import (
    assert_windows_efi,
    check_vm_xml_hyperv,
    check_windows_vm_hvinfo,
    validate_pause_unpause_windows_vm,
)
from utilities.ssp import validate_os_info_vmi_vs_windows_os
from utilities.virt import (
    check_vm_xml_smbios,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    validate_virtctl_guest_agent_after_guest_reboot,
    validate_virtctl_guest_agent_data_over_time,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.special_infra,
    pytest.mark.high_resource_vm,
    pytest.mark.data_collector_scope(scope="module"),
]

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonTemplatesWindows"


@pytest.mark.windows
class TestCommonTemplatesWindows:
    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    def test_create_vm(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-2196

        Test CNV VM creation from template
        """

        LOGGER.info("Create VM from template.")
        matrix_windows_os_vm_from_template.create(wait=True)

    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    def test_start_vm(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-3785

        Test CNV common templates VM initiation
        """

        running_vm(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_efi_secureboot_enabled_by_default(self, admin_client, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-12642 # <skip-jira-utils-check>
        Polarion: CNV-8854

        Test CNV common templates EFI secureboot status
        """

        assert_windows_efi(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vmi_guest_agent_info", depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_vmi_guest_agent_info(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1013 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-3512

        Test Guest OS agent info.
        """
        validate_os_info_vmi_vs_windows_os(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_virtctl_guest_agent_os_info(self, admin_client, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1013 # <skip-jira-utils-check>
        Polarion: CNV-4196
        """
        validate_os_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template, admin_client=admin_client)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_virtctl_guest_agent_fs_info(self, admin_client, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1013 # <skip-jira-utils-check>
        Polarion: CNV-4197
        """
        validate_fs_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template, admin_client=admin_client)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_virtctl_guest_agent_user_info(self, admin_client, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1013 # <skip-jira-utils-check>
        Polarion: CNV-4552
        """
        validate_user_info_virtctl_vs_windows_os(vm=matrix_windows_os_vm_from_template, admin_client=admin_client)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    def test_domain_label(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-3303

        CNV common templates 'domain' label contains vm name
        """
        vm = matrix_windows_os_vm_from_template
        domain_label = vm.body["spec"]["template"]["metadata"]["labels"]["kubevirt.io/domain"]
        assert domain_label == vm.name, f"Wrong domain label: {domain_label}"

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_hyperv(self, admin_client, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-989 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-1247 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/CNV-5968 # <skip-jira-utils-check>
        Polarion: CNV-2776
        """
        LOGGER.info("Verify VM HyperV values.")
        check_vm_xml_hyperv(
            vm=matrix_windows_os_vm_from_template,
            admin_client=admin_client,
            expected_hyperv_features=matrix_windows_os_vm_from_template.instance.spec.template.spec.domain.features.hyperv.to_dict(),
        )
        check_windows_vm_hvinfo(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_vm_machine_type(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-346 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-3674
        """
        check_machine_type(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_pause_unpause_vm(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1067 # <skip-jira-utils-check>
        Polarion: CNV-3087

        Test VM pause and unpause
        """
        validate_pause_unpause_windows_vm(vm=matrix_windows_os_vm_from_template)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_vm_smbios_default(self, admin_client, smbios_from_kubevirt_config, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1335 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/CNV-6437 # <skip-jira-utils-check>
        Polarion: CNV-4203
        """
        check_vm_xml_smbios(
            vm=matrix_windows_os_vm_from_template, cm_values=smbios_from_kubevirt_config, admin_client=admin_client
        )

    @pytest.mark.rwx_default_storage
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify", depends=[f"{TESTS_CLASS_NAME}::start_vm"]
    )
    def test_migrate_vm(self, admin_client: DynamicClient, matrix_windows_os_vm_from_template: VirtualMachineForTests):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-192 # <skip-jira-utils-check>
        Polarion: CNV-3335

        Test SSH connectivity after migration
        """
        migrate_vm_and_verify(vm=matrix_windows_os_vm_from_template, client=admin_client, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=matrix_windows_os_vm_from_template, admin_client=admin_client)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_pause_unpause_after_migrate(self, matrix_windows_os_vm_from_template, regedit_process_in_windows_os):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1067 # <skip-jira-utils-check>
        Polarion: CNV-5903
        """
        validate_pause_unpause_windows_vm(
            vm=matrix_windows_os_vm_from_template, pre_pause_pid=regedit_process_in_windows_os
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::migrate_vm_and_verify"])
    def test_verify_virtctl_guest_agent_data_after_migrate(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1220 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/CNV-5015 # <skip-jira-utils-check>
        Polarion: CNV-6009
        """
        assert validate_virtctl_guest_agent_data_over_time(vm=matrix_windows_os_vm_from_template), (
            "Guest agent stopped responding"
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vmi_guest_agent_info"])
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: Intermittent failures due to timeout exceeded; tracked in CNV-79605",
        run=False,
    )
    def test_vmi_guest_agent_info_after_guest_reboot(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-1013 # <skip-jira-utils-check>
        Polarion: CNV-12220
        """
        validate_virtctl_guest_agent_after_guest_reboot(
            vm=matrix_windows_os_vm_from_template, os_type=OS_FLAVOR_WINDOWS
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    def test_vm_deletion(self, matrix_windows_os_vm_from_template):
        """
        Jira: https://redhat.atlassian.net/browse/KNIP-810 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-811 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-813 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/KNIP-812 # <skip-jira-utils-check>
        Polarion: CNV-3289

        Test CNV common templates VM deletion
        """
        matrix_windows_os_vm_from_template.delete(wait=True)
