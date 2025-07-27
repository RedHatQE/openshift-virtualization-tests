"""
WSL2 test
Note: The windows image runs the WSL guest (Fedora-33) at boot.
"""

import logging
import re
import shlex

import pytest
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.virt.utils import verify_wsl2_guest_works
from utilities.constants import TCP_TIMEOUT_30SEC, Images
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_windows_os_dict,
    migrate_vm_and_verify,
    running_vm,
)

pytestmark = [pytest.mark.special_infra, pytest.mark.high_resource_vm]


LOGGER = logging.getLogger(__name__)
RESOURCE_USAGES = 70.0
TESTS_CLASS_NAME = "TestWSL2"


def get_windows_vm_resource_usage(vm):
    """
    Running python script to get cpu and memory usage output like:
    'Windows VM CPU and Memory usage: The CPU usage: 0.9, Memory used(RAM):20.5
    (20.5, 0.9)'
    """
    usage = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("python C:\\\\tools\\\\cpu_mem_usage.py"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]
    LOGGER.info(f"Windows VM CPU and Memory usage: {usage}")
    out = re.search(r".*CPU usage: (?P<cpu>.*),.*\(RAM\):(?P<ram>.*)", usage)
    return float(out.group("cpu")), float(out.group("ram"))


def assert_windows_host_resource_usage(vm):
    cpu, ram = get_windows_vm_resource_usage(vm=vm)
    assert float(cpu) < RESOURCE_USAGES, f"CPU usage on the Windows VM is higher than {RESOURCE_USAGES}"
    assert float(ram) < RESOURCE_USAGES, f"Memory usage on the Windows VM is higher than {RESOURCE_USAGES}"


@pytest.fixture(scope="class")
def windows_wsl2_vm(
    request,
    namespace,
    unprivileged_client,
    golden_image_data_source_scope_class,
    modern_cpu_for_migration,
    vm_cpu_flags,
):
    """Create Windows 10/11 VM, Run VM and wait for WSL2 guest to start"""
    win_ver = request.param["win_ver"]
    with VirtualMachineForTestsFromTemplate(
        name=f"{win_ver}-wsl2",
        labels=Template.generate_template_labels(**get_windows_os_dict(windows_version=win_ver)["template_labels"]),
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
        cpu_model=modern_cpu_for_migration,
        cpu_flags=vm_cpu_flags,
        memory_guest=Images.Windows.DEFAULT_MEMORY_SIZE_WSL,
        cpu_cores=8,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def migrated_wsl2_vm(windows_wsl2_vm):
    migrate_vm_and_verify(vm=windows_wsl2_vm, check_ssh_connectivity=True)
    return windows_wsl2_vm


@pytest.mark.ibm_bare_metal
@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, windows_wsl2_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-win10-wsl2",
                "image": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN10_WSL2_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {"win_ver": "win-10"},
            id="Windows-10",
        ),
        pytest.param(
            {
                "dv_name": "dv-win11-wsl2",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_WSL2_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {"win_ver": "win-11"},
            id="Windows-11",
        ),
    ],
    indirect=True,
)
class TestWSL2:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::wsl2_guest")
    @pytest.mark.polarion("CNV-6023")
    def test_wsl2_guest(self, windows_wsl2_vm):
        verify_wsl2_guest_works(vm=windows_wsl2_vm)
        assert_windows_host_resource_usage(vm=windows_wsl2_vm)

    @pytest.mark.rwx_default_storage
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::wsl2_guest"])
    @pytest.mark.polarion("CNV-5462")
    def test_migration_with_wsl2_guest(self, migrated_wsl2_vm):
        verify_wsl2_guest_works(vm=migrated_wsl2_vm)
        assert_windows_host_resource_usage(vm=migrated_wsl2_vm)
