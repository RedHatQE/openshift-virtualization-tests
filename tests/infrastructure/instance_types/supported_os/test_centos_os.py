import pytest

from tests.infrastructure.instance_types.supported_os.constants import TEST_CREATE_VM_TEST_NAME, TEST_START_VM_TEST_NAME
from utilities.constants.instance_types import (
    PREFERENCE_STR,
    U1_MEDIUM_STR,
)
from utilities.virt import (
    check_qemu_guest_agent_installed,
    running_vm,
    wait_for_console,
)

pytestmark = pytest.mark.post_upgrade

TESTS_MODULE_IDENTIFIER = "TestCommonInstancetypeCentos"


@pytest.mark.arm64
@pytest.mark.sno
@pytest.mark.s390x
class TestVMCreationAndValidation:
    @pytest.mark.dependency(name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}")
    def test_create_vm(self, golden_image_centos_vm_with_instance_type, instance_type_centos_os_matrix__module__):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-33839 # <skip-jira-utils-check>
        Polarion: CNV-12068
        """
        golden_image_centos_vm_with_instance_type.create(wait=True)
        os_param_dict = instance_type_centos_os_matrix__module__[[*instance_type_centos_os_matrix__module__][0]]
        assert golden_image_centos_vm_with_instance_type.instance.spec.instancetype.name == U1_MEDIUM_STR
        assert golden_image_centos_vm_with_instance_type.instance.spec.preference.name == os_param_dict[PREFERENCE_STR]

    @pytest.mark.dependency(
        name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}",
        depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"],
    )
    def test_start_vm(self, golden_image_centos_vm_with_instance_type):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-33839 # <skip-jira-utils-check>
        Polarion: CNV-12069
        """
        running_vm(vm=golden_image_centos_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    def test_vm_console(self, golden_image_centos_vm_with_instance_type):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-33839 # <skip-jira-utils-check>
        Polarion: CNV-12070
        """
        wait_for_console(vm=golden_image_centos_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    def test_vmi_guest_agent_exists(self, golden_image_centos_vm_with_instance_type):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-33839 # <skip-jira-utils-check>
        Polarion: CNV-12071
        """
        assert check_qemu_guest_agent_installed(ssh_exec=golden_image_centos_vm_with_instance_type.ssh_exec), (
            "qemu guest agent package is not installed"
        )


@pytest.mark.arm64
@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.order(-1)
class TestVMDeletion:
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"])
    def test_vm_deletion(self, golden_image_centos_vm_with_instance_type):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-33839 # <skip-jira-utils-check>
        Polarion: CNV-12078
        """
        golden_image_centos_vm_with_instance_type.delete(wait=True)
