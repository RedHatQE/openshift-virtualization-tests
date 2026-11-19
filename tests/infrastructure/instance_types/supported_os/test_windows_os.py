import logging

import pytest

from utilities.guest_support import (
    assert_windows_efi,
    check_vm_xml_hyperv,
    check_windows_vm_hvinfo,
    validate_pause_unpause_windows_vm,
)
from utilities.virt import running_vm

pytestmark = [pytest.mark.high_resource_vm, pytest.mark.special_infra, pytest.mark.tier3, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCommonPreferenceWindows"


@pytest.mark.windows
class TestCommonPreferenceWindows:
    """
    Tests for supporting Windows os when using a VM with instance types.

    Jira: https://redhat.atlassian.net/browse/CNV-92873  # <skip-jira-utils-check>
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::create_vm")
    def test_create_vm(
        self,
        golden_image_windows_vm,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-12269
        """
        LOGGER.info("Create VM from preference.")
        golden_image_windows_vm.create(wait=True)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::start_vm", depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    def test_start_vm(self, golden_image_windows_vm):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-12270
        """
        running_vm(vm=golden_image_windows_vm)

    # all the tests following this comment depend on start_vm: requires a running VM
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_efi_secureboot_enabled(self, golden_image_windows_vm):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-12387
        """
        assert_windows_efi(vm=golden_image_windows_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_hyperv(self, admin_client, golden_image_windows_vm):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-12388
        """
        check_vm_xml_hyperv(
            vm=golden_image_windows_vm,
            admin_client=admin_client,
            expected_hyperv_features=golden_image_windows_vm.vmi.instance.spec.domain.features.hyperv.to_dict(),
        )
        check_windows_vm_hvinfo(vm=golden_image_windows_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::start_vm"])
    def test_pause_unpause_vm(self, golden_image_windows_vm):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-16330
        """
        validate_pause_unpause_windows_vm(vm=golden_image_windows_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::create_vm"])
    def test_vm_deletion(self, golden_image_windows_vm):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-24867 # <skip-jira-utils-check>
        Polarion: CNV-12271
        """
        golden_image_windows_vm.delete(wait=True)
