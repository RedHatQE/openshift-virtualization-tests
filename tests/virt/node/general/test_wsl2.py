"""
WSL2 test
Note: The windows image runs the WSL guest (Fedora-33) at boot.
"""

import logging
import os
import re
import shlex

import pytest
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.virt.utils import verify_wsl2_guest_running
from utilities.constants import TCP_TIMEOUT_30SEC, Images
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_windows_os_dict,
    migrate_vm_and_verify,
    running_vm,
)

pytestmark = pytest.mark.usefixtures("skip_on_psi_cluster")

LOGGER = logging.getLogger(__name__)
RESOURCE_USAGES = 70.0
TESTS_CLASS_NAME = "TestWSL2"


def get_wsl_pid(vm):
    """
    Run on the VM the command: 'tasklist' and return the pid for wsl.exe
    output 'tasklist' => here pid is 8816:
    ....
    wsl.exe                       8816 Console                    1      4,144 K
    ....
    """
    res = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("tasklist"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )
    wsl_pid = re.search(r"wsl.exe.*?(\d+).*?", res[0])
    assert wsl_pid, f"Missing pid for wsl.exe, task list: \n{res[0]}"
    return wsl_pid.group(1)


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
        cpu_cores=16,
        cpu_threads=1,  # TODO: Remove once WSL2 image is fixed to work with multi-threads
    ) as vm:
        running_vm(vm=vm)
        verify_wsl2_guest_running(vm=vm)
        yield vm


@pytest.mark.ibm_bare_metal
@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, windows_wsl2_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-win10-wsl2",
                "image": os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN10_WSL2_IMG),
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {"win_ver": "win-10"},
            id="Windows-10",
        ),
        pytest.param(
            {
                "dv_name": "dv-win11-wsl2",
                "image": os.path.join(Images.Windows.DIR, Images.Windows.WIN11_WSL2_IMG),
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
    @staticmethod
    def _check_usage(resource_usage, resource_type):
        assert float(resource_usage) < RESOURCE_USAGES, (
            f"{resource_type} usage on the Windows VM is higher then {RESOURCE_USAGES}"
        )

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::wsl2_guest")
    @pytest.mark.polarion("CNV-6023")
    def test_wsl2_guest(
        self,
        golden_image_data_volume_scope_class,
        windows_wsl2_vm,
    ):
        resource_usage = get_windows_vm_resource_usage(vm=windows_wsl2_vm)
        self._check_usage(resource_usage=resource_usage[0], resource_type="CPU")
        self._check_usage(resource_usage=resource_usage[1], resource_type="Memory")

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::wsl2_guest"])
    @pytest.mark.polarion("CNV-5462")
    def test_migration_with_wsl2_guest(
        self,
        skip_if_no_common_modern_cpu,
        skip_access_mode_rwo_scope_function,
        golden_image_data_volume_scope_class,
        windows_wsl2_vm,
    ):
        wsl_pid_before = get_wsl_pid(vm=windows_wsl2_vm)
        LOGGER.info(f"PID before migration: {wsl_pid_before}")
        migrate_vm_and_verify(vm=windows_wsl2_vm, check_ssh_connectivity=True)
        verify_wsl2_guest_running(vm=windows_wsl2_vm)
        wsl_pid_after = get_wsl_pid(vm=windows_wsl2_vm)
        LOGGER.info(f"PID after migration: {wsl_pid_after}")
        assert wsl_pid_before == wsl_pid_after, (
            f"WSL pid are not the same before and after migrate. before:{wsl_pid_before}, after:{wsl_pid_after}"
        )
        resource_usage = get_windows_vm_resource_usage(vm=windows_wsl2_vm)
        self._check_usage(resource_usage=resource_usage[0], resource_type="CPU")
        self._check_usage(resource_usage=resource_usage[1], resource_type="Memory")
