import pytest

from utilities.constants import INSTANCE_TYPE_STR, PREFERENCE_STR
from utilities.virt import (
    check_qemu_guest_agent_installed,
    migrate_vm_and_verify,
    running_vm,
    validate_libvirt_persistent_domain,
    wait_for_console,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating]


TESTS_CLASS_NAME = "TestCommonInstanceTypeRhel"
CREATE_VM_TEST_NAME = f"{TESTS_CLASS_NAME}::create_vm"
START_VM_TEST_NAME = f"{TESTS_CLASS_NAME}::start_vm"


class TestCommonInstanceTypeRhel:
    @pytest.mark.sno
    @pytest.mark.dependency(name=CREATE_VM_TEST_NAME)
    @pytest.mark.polarion("CNV-11710")
    def test_create_vm(
        self,
        golden_image_vm_with_instance_type,
        instance_type_rhel_os_matrix__class__,
    ):
        golden_image_vm_with_instance_type.create(wait=True)
        os_param_dict = instance_type_rhel_os_matrix__class__[[*instance_type_rhel_os_matrix__class__][0]]
        assert golden_image_vm_with_instance_type.instance.spec.instancetype.name == os_param_dict[INSTANCE_TYPE_STR]
        assert golden_image_vm_with_instance_type.instance.spec.preference.name == os_param_dict[PREFERENCE_STR]

    @pytest.mark.sno
    @pytest.mark.dependency(name=START_VM_TEST_NAME, depends=[CREATE_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-11711")
    def test_start_vm(self, golden_image_vm_with_instance_type):
        running_vm(
            vm=golden_image_vm_with_instance_type,
        )

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[START_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-11712")
    def test_vm_console(self, golden_image_vm_with_instance_type):
        wait_for_console(vm=golden_image_vm_with_instance_type)

    @pytest.mark.sno
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::vmi_guest_agent",
        depends=[START_VM_TEST_NAME],
    )
    @pytest.mark.polarion("CNV-11713")
    def test_vmi_guest_agent_exists(self, golden_image_vm_with_instance_type):
        assert check_qemu_guest_agent_installed(ssh_exec=golden_image_vm_with_instance_type.ssh_exec), (
            "qemu guest agent package is not installed"
        )

    @pytest.mark.polarion("CNV-11714")
    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::migrate_vm_and_verify",
        depends=[START_VM_TEST_NAME],
    )
    def test_migrate_vm(
        self,
        skip_if_no_common_modern_cpu,
        skip_access_mode_rwo_scope_class,
        golden_image_vm_with_instance_type,
    ):
        migrate_vm_and_verify(vm=golden_image_vm_with_instance_type, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=golden_image_vm_with_instance_type)

    @pytest.mark.sno
    @pytest.mark.dependency(depends=[CREATE_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-11715")
    def test_vm_deletion(self, golden_image_vm_with_instance_type):
        golden_image_vm_with_instance_type.delete(wait=True)
