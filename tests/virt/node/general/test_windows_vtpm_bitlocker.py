import logging
import shlex

import pytest
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.utils import update_hco_with_persistent_storage_config
from utilities.constants import TIMEOUT_2MIN, TIMEOUT_40MIN, Images
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_windows_os_dict,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

pytestmark = [pytest.mark.tier3, pytest.mark.ibm_bare_metal, pytest.mark.special_infra, pytest.mark.high_resource_vm]

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestBitLockerVTPM"


def verify_tpm_in_os(vm):
    vtpm_enabled = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(
            r"wmic /namespace:\\root\cimv2\security\microsofttpm path Win32_Tpm get IsEnabled_InitialValue",
            posix=False,
        ),
    )[0]
    assert "TRUE" in vtpm_enabled, "TPM is not present/enabled in OS!"


def enable_bitlocker(vm):
    def _wait_encryption_finish(vm):
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_40MIN,
            sleep=TIMEOUT_2MIN,
            func=run_ssh_commands,
            host=vm.ssh_exec,
            commands=shlex.split("manage-bde -status c:"),
        )

        try:
            for sample in sampler:
                if sample:
                    if all([
                        True if msg in sample[0] else False for msg in ["100.0%", "Fully Encrypted", "Protection On"]
                    ]):
                        return
        except TimeoutExpiredError:
            LOGGER.error("Failed to encrypt disk")
            raise

    if "win-2022" in vm.name:
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split('powershell -c "install-windowsfeature bitlocker"'),
        )
        restart_vm_wait_for_running_vm(vm=vm)

    run_ssh_commands(host=vm.ssh_exec, commands=shlex.split('powershell -c "initialize-tpm"'))
    run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("manage-bde -on c: -s"))
    _wait_encryption_finish(vm=vm)


@pytest.fixture(scope="class")
def file_system_persistent_storage_hco_config(
    request,
    hyperconverged_resource_scope_module,
    rwx_fs_available_storage_classes_names,
):
    if request.param["rwx_access_mode"]:
        if not rwx_fs_available_storage_classes_names:
            pytest.fail("No RWX FS supported storage class available on cluster!")
        storage_class = rwx_fs_available_storage_classes_names[0]
    else:
        storage_class = py_config["default_storage_class"]

    with update_hco_with_persistent_storage_config(
        hco_cr=hyperconverged_resource_scope_module,
        storage_class=storage_class,
    ):
        yield


@pytest.fixture(scope="class")
def windows_vtpm_vm(
    request,
    namespace,
    unprivileged_client,
    file_system_persistent_storage_hco_config,
    golden_image_data_source_scope_class,
    modern_cpu_for_migration,
):
    windows_version = request.param["windows_version"]
    presistent_enabled = {"persistent": True}
    with VirtualMachineForTestsFromTemplate(
        name=f"{windows_version}-vtpm-vm",
        labels=Template.generate_template_labels(
            **get_windows_os_dict(windows_version=windows_version)["template_labels"]
        ),
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
        tpm_params=presistent_enabled,
        efi_params=presistent_enabled,
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        verify_tpm_in_os(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def bitlocker_encrypted_vm(windows_vtpm_vm):
    enable_bitlocker(vm=windows_vtpm_vm)
    return windows_vtpm_vm


@pytest.fixture(scope="class")
def migrated_encrypted_vm(bitlocker_encrypted_vm):
    migrate_vm_and_verify(vm=bitlocker_encrypted_vm, check_ssh_connectivity=True)
    return bitlocker_encrypted_vm


@pytest.mark.parametrize(
    "file_system_persistent_storage_hco_config, golden_image_data_volume_scope_class, windows_vtpm_vm",
    [
        pytest.param(
            {"rwx_access_mode": False},
            {
                "dv_name": "dv-win11-vtpm-vm",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {"windows_version": "win-11"},
            id="Windows-11",
        ),
        pytest.param(
            {"rwx_access_mode": True},
            {
                "dv_name": "dv-win2022-vtpm-vm",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN2022_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {"windows_version": "win-2022"},
            id="Windows-2k22",
        ),
    ],
    indirect=True,
)
class TestBitLockerVTPM:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::persistent_tpm")
    @pytest.mark.polarion("CNV-10318")
    def test_persistent_tpm(self, windows_vtpm_vm):
        xml_dict_tpm = windows_vtpm_vm.privileged_vmi.xml_dict["domain"]["devices"]["tpm"]
        assert xml_dict_tpm["@model"] == "tpm-crb", "TPM model should be tpm-crb!"
        assert xml_dict_tpm["backend"].get("@persistent_state") == "yes", "TPM is not peristent state in dumpxml!"

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::bitlocker_encryption",
        depends=[f"{TESTS_CLASS_NAME}::persistent_tpm"],
    )
    @pytest.mark.polarion("CNV-10308")
    def test_bitlocker_encryption(self, bitlocker_encrypted_vm):
        restart_vm_wait_for_running_vm(vm=bitlocker_encrypted_vm)

    @pytest.mark.rwx_default_storage
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::bitlocker_encryption"])
    @pytest.mark.polarion("CNV-10309")
    def test_migrate_encrypted_vm(self, migrated_encrypted_vm):
        restart_vm_wait_for_running_vm(vm=migrated_encrypted_vm)
