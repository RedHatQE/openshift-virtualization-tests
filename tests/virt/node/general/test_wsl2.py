"""
WSL2 test
Note: The windows image runs the WSL guest (Fedora-33) at boot.
"""

import logging
import re
import shlex

import pytest
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_instancetype import VirtualMachineInstancetype
from ocp_resources.virtual_machine_preference import VirtualMachinePreference
from pyhelper_utils.shell import run_ssh_commands

from tests.utils import verify_wsl2_guest_works
from tests.virt.constants import WINDOWS_10_WSL, WINDOWS_11_WSL
from utilities.constants import OS_FLAVOR_WINDOWS, TCP_TIMEOUT_30SEC, Images
from utilities.virt import (
    VirtualMachineForTests,
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
def wsl2_vm_instance_type(unprivileged_client, namespace):
    with VirtualMachineInstancetype(
        client=unprivileged_client,
        namespace=namespace.name,
        name="wsl2-windows-instance-type",
        cpu={"guest": 12},
        memory={"guest": Images.Windows.DEFAULT_MEMORY_SIZE_WSL},
    ) as instance_type:
        yield instance_type


@pytest.fixture(scope="class")
def windows_wsl2_vm_preference(request, unprivileged_client, namespace):
    """Windows VM preference with CPU topology set to 'cores' for better performance."""
    windows_preference_name = request.param
    base_preference = VirtualMachineClusterPreference(client=unprivileged_client, name=windows_preference_name)
    base_spec = base_preference.instance.to_dict()["spec"]

    with VirtualMachinePreference(
        client=unprivileged_client,
        namespace=namespace.name,
        name=f"wsl2-{windows_preference_name}-preference",
        cpu={"preferredCPUTopology": "cores"},
        clock=base_spec.get("clock"),
        devices=base_spec.get("devices"),
        features=base_spec.get("features"),
        firmware=base_spec.get("firmware"),
        requirements=base_spec.get("requirements"),
    ) as preference:
        yield preference


@pytest.fixture(scope="class")
def windows_wsl2_vm(
    namespace,
    unprivileged_client,
    wsl2_vm_instance_type,
    windows_wsl2_vm_preference,
    golden_image_data_volume_template_for_test_scope_class,
    modern_cpu_for_migration,
    vm_cpu_flags,
):
    """Create Windows 10/11 VM, Run VM and wait for WSL2 guest to start"""
    with VirtualMachineForTests(
        name="win-wsl2",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=wsl2_vm_instance_type,
        vm_preference=windows_wsl2_vm_preference,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        cpu_model=modern_cpu_for_migration,
        cpu_flags=vm_cpu_flags,
        os_flavor=OS_FLAVOR_WINDOWS,
        disk_type=None,
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
    "golden_image_data_source_for_test_scope_class, windows_wsl2_vm_preference",
    [
        pytest.param(
            {"os_dict": WINDOWS_10_WSL},
            "windows.10",
            id="Windows-10",
        ),
        pytest.param(
            {"os_dict": WINDOWS_11_WSL},
            "windows.11",
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
