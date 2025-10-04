import pytest

from tests.infrastructure.instance_types.supported_os.constants import (
    TEST_CREATE_VM_TEST_NAME,
    TEST_START_VM_TEST_NAME,
    TESTS_MIGRATE_VM,
)
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
    migrate_vm_and_verify,
    running_vm,
    update_vm_efi_spec_and_restart,
    validate_libvirt_persistent_domain,
    validate_pause_optional_migrate_unpause_linux_vm,
    validate_virtctl_guest_agent_data_over_time,
    wait_for_console,
)

pytestmark = [pytest.mark.post_upgrade]

TESTS_MODULE_IDENTIFIER = "TestCommonInstancetypeRhel"


@pytest.mark.arm64
@pytest.mark.s390x
@pytest.mark.smoke
@pytest.mark.gating
@pytest.mark.sno
class TestVMCreationAndValidation:
    @pytest.mark.dependency(name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}")
    @pytest.mark.polarion("CNV-11710")
    def test_create_vm(self, golden_image_rhel_vm_with_instance_type, instance_type_rhel_os_matrix__module__):
        golden_image_rhel_vm_with_instance_type.create(wait=True)
        os_param_dict = instance_type_rhel_os_matrix__module__[[*instance_type_rhel_os_matrix__module__][0]]
        assert golden_image_rhel_vm_with_instance_type.instance.spec.instancetype.name == U1_MEDIUM_STR
        assert golden_image_rhel_vm_with_instance_type.instance.spec.preference.name == os_param_dict[PREFERENCE_STR]

    @pytest.mark.dependency(
        name=f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}",
        depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"],
    )
    @pytest.mark.polarion("CNV-11711")
    def test_start_vm(self, golden_image_rhel_vm_with_instance_type):
        running_vm(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11712")
    def test_vm_console(self, golden_image_rhel_vm_with_instance_type):
        wait_for_console(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11829")
    def test_expose_ssh(self, golden_image_rhel_vm_with_instance_type):
        assert golden_image_rhel_vm_with_instance_type.ssh_exec.executor().is_connective(tcp_timeout=120), (
            "Failed to login via SSH"
        )

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11713")
    def test_vmi_guest_agent_exists(self, golden_image_rhel_vm_with_instance_type):
        assert check_qemu_guest_agent_installed(ssh_exec=golden_image_rhel_vm_with_instance_type.ssh_exec), (
            "qemu guest agent package is not installed"
        )


@pytest.mark.usefixtures("xfail_if_rhel8")
@pytest.mark.sno
class TestVMFeatures:
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11830")
    def test_system_boot_mode(self, golden_image_rhel_vm_with_instance_type):
        assert_linux_efi(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.polarion("CNV-11831")
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    def test_efi_secureboot_enabled_initial_boot(self, golden_image_rhel_vm_with_instance_type):
        assert_secure_boot_dmesg(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11832")
    def test_efi_secureboot_enabled_guest_os(self, golden_image_rhel_vm_with_instance_type):
        assert_secure_boot_mokutil_status(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11833")
    def test_efi_secureboot_enabled_lockdown_state(self, golden_image_rhel_vm_with_instance_type):
        assert_kernel_lockdown_mode(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11834")
    def test_efi_secureboot_disabled_and_enabled(
        self,
        golden_image_rhel_vm_with_instance_type,
    ):
        vm = golden_image_rhel_vm_with_instance_type

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
    def test_vm_smbios_default(self, smbios_from_kubevirt_config, golden_image_rhel_vm_with_instance_type):
        check_vm_xml_smbios(vm=golden_image_rhel_vm_with_instance_type, cm_values=smbios_from_kubevirt_config)


@pytest.mark.arm64
@pytest.mark.s390x
class TestVMMigrationAndState:
    @pytest.mark.polarion("CNV-11714")
    @pytest.mark.dependency(
        name=f"{TESTS_MODULE_IDENTIFIER}::{TESTS_MIGRATE_VM}",
        depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_START_VM_TEST_NAME}"],
    )
    def test_migrate_vm(self, skip_access_mode_rwo_scope_class, golden_image_rhel_vm_with_instance_type):
        migrate_vm_and_verify(vm=golden_image_rhel_vm_with_instance_type, check_ssh_connectivity=True)
        validate_libvirt_persistent_domain(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.polarion("CNV-11836")
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TESTS_MIGRATE_VM}"])
    def test_pause_unpause_vm(self, golden_image_rhel_vm_with_instance_type):
        validate_pause_optional_migrate_unpause_linux_vm(vm=golden_image_rhel_vm_with_instance_type)

    @pytest.mark.polarion("CNV-11837")
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TESTS_MIGRATE_VM}"])
    def test_pause_unpause_after_migrate(self, golden_image_rhel_vm_with_instance_type, ping_process_in_rhel_os):
        validate_pause_optional_migrate_unpause_linux_vm(
            vm=golden_image_rhel_vm_with_instance_type,
            pre_pause_pid=ping_process_in_rhel_os(golden_image_rhel_vm_with_instance_type),
        )

    @pytest.mark.polarion("CNV-11838")
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TESTS_MIGRATE_VM}"])
    def test_verify_virtctl_guest_agent_data_after_migrate(self, golden_image_rhel_vm_with_instance_type):
        assert validate_virtctl_guest_agent_data_over_time(vm=golden_image_rhel_vm_with_instance_type), (
            "Guest agent stopped responding"
        )


@pytest.mark.arm64
@pytest.mark.s390x
@pytest.mark.smoke
@pytest.mark.gating
@pytest.mark.sno
@pytest.mark.order(-1)
class TestVMDeletion:
    @pytest.mark.dependency(depends=[f"{TESTS_MODULE_IDENTIFIER}::{TEST_CREATE_VM_TEST_NAME}"])
    @pytest.mark.polarion("CNV-11715")
    def test_vm_deletion(self, golden_image_rhel_vm_with_instance_type):
        golden_image_rhel_vm_with_instance_type.delete(wait=True)
