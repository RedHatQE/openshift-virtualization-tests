import shlex

from pyhelper_utils.shell import run_ssh_commands

from tests.virt.node.gpu.constants import VGPU_DEVICE_NAME_STR
from tests.virt.utils import fetch_gpu_device_name_from_vm_instance, verify_gpu_device_exists_in_vm
from utilities.constants import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_3MIN,
    NamespacesNames,
)
from utilities.infra import get_daemonsets
from utilities.virt import restart_vm_wait_for_running_vm, running_vm


def restart_and_check_gpu_exists(vm, supported_gpu_device):
    restart_vm_wait_for_running_vm(vm=vm, ssh_timeout=TIMEOUT_3MIN)
    verify_gpu_device_exists_in_vm(vm=vm, supported_gpu_device=supported_gpu_device)


def verify_gpu_expected_count_updated_on_node(gpu_nodes, device_name, expected_count):
    device_expected_count_failed_checks = []
    for gpu_node in gpu_nodes:
        for status_type in ["allocatable", "capacity"]:
            resources = getattr(gpu_node.instance.status, status_type)
            if resources[device_name] != expected_count:
                device_expected_count_failed_checks.append({
                    gpu_node.name: {
                        f"device_{status_type}_count": {
                            "expected": expected_count,
                            "actual": resources[device_name],
                        }
                    }
                })
    assert not device_expected_count_failed_checks, f"Failed checks: {device_expected_count_failed_checks}"


def install_nvidia_drivers_on_windows_vm(vm, supported_gpu_device):
    # Installs NVIDIA Drivers placed on the Windows-11 or win2k19 Images.
    # vGPU uses NVIDIA GRID Drivers and GPU Passthrough uses normal NVIDIA Drivers.
    vgpu_device_name = supported_gpu_device[VGPU_DEVICE_NAME_STR]
    gpu_mode = "vgpu" if fetch_gpu_device_name_from_vm_instance(vm) == vgpu_device_name else "gpu"
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split(
                f"C:\\NVIDIA\\{gpu_mode}\\International\\setup.exe -s & exit /b 0",
                posix=False,
            )
        ],
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )
    # Wait for Running VM, as only vGPU VM Reboots after installing NVIDIA GRID Drivers.
    if fetch_gpu_device_name_from_vm_instance(vm=vm) == vgpu_device_name:
        running_vm(vm=vm)


def wait_for_manager_pods_deployed(admin_client, ds_name):
    daemonsets_in_namespace = get_daemonsets(admin_client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
    for ds in daemonsets_in_namespace:
        if ds_name in ds.name:
            ds.wait_until_deployed()
