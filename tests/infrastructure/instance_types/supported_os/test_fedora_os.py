import pytest

from tests.infrastructure.instance_types.supported_os.constants import TEST_CREATE_VM_TEST_NAME, TEST_START_VM_TEST_NAME
from tests.infrastructure.instance_types.utils import (
    assert_kernel_lockdown_mode,
    assert_secure_boot_dmesg,
    assert_secure_boot_mokutil_status,
)
from utilities.constants import PREFERENCE_STR, U1_MEDIUM_STR
from utilities.virt import (
    assert_linux_efi,
    assert_vm_xml_efi,
    check_qemu_guest_agent_installed,
    check_vm_xml_smbios,
    running_vm,
    update_vm_efi_spec_and_restart,
    wait_for_console,
)

TESTS_MODULE_IDENTIFIER = "TestCommonInstancetypeFedora"


@pytest.mark.arm64
@pytest.mark.sno
@pytest.mark.s390x
class TestVMCreationAndValidation:
    @pytest.mark.dependency(name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}")
    @pytest.mark.polarion("CNV-12068")
    def test_create_vm(self, golden_image_fedora_vm_with_instance_type, instance_type_fedora_os_matrix__module__):
        golden_image_fedora_vm_with_instance_type.create(wait=True)
        os_param_dict = instance_type_fedora_os_matrix__module__[[*instance_type_fedora_os_matrix__module__][0]]
        assert golden_image_fedora_vm_with_instance_type.instance.spec.instancetype.name == U1_MEDIUM_STR
        assert golden_image_fedora_vm_with_instance_type.instance.spec.preference.name == os_param_dict[PREFERENCE_STR]

    @pytest.mark.dependency(
        name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}",
        depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"],
    )
    @pytest.mark.polarion("CNV-12069")
    def test_start_vm(self, golden_image_fedora_vm_with_instance_type):
        running_vm(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-12070")
    def test_vm_console(self, golden_image_fedora_vm_with_instance_type):
        wait_for_console(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-12071")
    def test_vmi_guest_agent_exists(self, golden_image_fedora_vm_with_instance_type):
        assert check_qemu_guest_agent_installed(ssh_exec=golden_image_fedora_vm_with_instance_type.ssh_exec), (
            "qemu guest agent package is not installed"
        )


@pytest.mark.sno
class TestVMFeatures:
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11830")
    def test_system_boot_mode(self, golden_image_fedora_vm_with_instance_type):
        assert_linux_efi(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.polarion("CNV-11831")
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    def test_efi_secureboot_enabled_initial_boot(self, golden_image_fedora_vm_with_instance_type):
        assert_secure_boot_dmesg(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11832")
    def test_efi_secureboot_enabled_guest_os(self, golden_image_fedora_vm_with_instance_type):
        assert_secure_boot_mokutil_status(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11833")
    def test_efi_secureboot_enabled_lockdown_state(self, golden_image_fedora_vm_with_instance_type):
        assert_kernel_lockdown_mode(vm=golden_image_fedora_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11834")
    def test_efi_secureboot_disabled_and_enabled(
        self,
        golden_image_fedora_vm_with_instance_type,
    ):
        vm = golden_image_fedora_vm_with_instance_type

        def _update_and_verify_secure_boot(vm, secure_boot_value):
            update_vm_efi_spec_and_restart(vm=vm, spec={"secureBoot": secure_boot_value})
            # assert vm config at hypervisor level
            assert_vm_xml_efi(vm=vm, secure_boot_enabled=secure_boot_value)
            assert_linux_efi(vm=vm)

        # Disable secureboot
        _update_and_verify_secure_boot(vm=vm, secure_boot_value=False)
        # Re-enable Secure Boot
        _update_and_verify_secure_boot(vm=vm, secure_boot_value=True)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11835")
    def test_vm_smbios_default(self, smbios_from_kubevirt_config, golden_image_fedora_vm_with_instance_type):
        check_vm_xml_smbios(vm=golden_image_fedora_vm_with_instance_type, cm_values=smbios_from_kubevirt_config)


@pytest.mark.arm64
@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.order(-1)
class TestVMDeletion:
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-12078")
    def test_vm_deletion(self, golden_image_fedora_vm_with_instance_type):
        golden_image_fedora_vm_with_instance_type.delete(wait=True)
