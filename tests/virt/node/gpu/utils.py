import logging
import shlex

from ocp_resources.resource import ResourceEditor
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from tests.virt.node.gpu.constants import (
    SANDBOX_VALIDATOR_DEPLOY_LABEL,
    VGPU_DEVICE_MANAGER_DEPLOY_LABEL,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.utils import fetch_gpu_device_name_from_vm_instance, verify_gpu_device_exists_in_vm
from utilities.constants import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
)
from utilities.virt import restart_vm_wait_for_running_vm, running_vm

LOGGER = logging.getLogger(__name__)


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
    # Installs NVIDIA Drivers placed on the Windows-10 or win2k19 Images.
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


def wait_for_ds_ready(ds, expected):
    """Wait for a DaemonSet to reach the expected number of ready pods.

    Args:
        ds (DaemonSet): DaemonSet object to watch.
        expected (int): expected number of ready pods.
    """
    LOGGER.info(f"{ds.name}: waiting for numberReady to reach {expected}")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: ds.instance.status.desiredNumberScheduled == ds.instance.status.numberReady == expected,
    ):
        if sample:
            LOGGER.info(f"{ds.name}: numberReady reached {expected}")
            break


def apply_node_labels(nodes, labels):
    ResourceEditor(patches={node: {"metadata": {"labels": labels}} for node in nodes}).update()


def toggle_vgpu_deploy_labels(gpu_nodes, nodes_with_supported_gpus, sandbox_validator_ds, vgpu_device_manager_ds):
    """Trigger a restart of sandbox-validator and vgpu-device-manager DaemonSets.

    The GPU operator does not automatically start sandbox-validator
    after the vgpu.config label is applied. Cycling their deploy labels forces a restart
    so they initialize correctly for vGPU workloads.

    Args:
        gpu_nodes (list): all GPU nodes.
        nodes_with_supported_gpus (list): vGPU-supported nodes.
        sandbox_validator_ds (DaemonSet): nvidia-sandbox-validator DaemonSet object.
        vgpu_device_manager_ds (DaemonSet): nvidia-vgpu-device-manager DaemonSet object.
    """
    LOGGER.info("Disabling sandbox-validator and vgpu-device-manager on GPU nodes")
    apply_node_labels(nodes=gpu_nodes, labels={SANDBOX_VALIDATOR_DEPLOY_LABEL: "false"})
    apply_node_labels(nodes=nodes_with_supported_gpus, labels={VGPU_DEVICE_MANAGER_DEPLOY_LABEL: "false"})
    try:
        wait_for_ds_ready(ds=sandbox_validator_ds, expected=0)
        wait_for_ds_ready(ds=vgpu_device_manager_ds, expected=0)
    finally:
        LOGGER.info("Re-enabling sandbox-validator and vgpu-device-manager on GPU nodes")
        apply_node_labels(nodes=gpu_nodes, labels={SANDBOX_VALIDATOR_DEPLOY_LABEL: "true"})
        apply_node_labels(nodes=nodes_with_supported_gpus, labels={VGPU_DEVICE_MANAGER_DEPLOY_LABEL: "true"})
    wait_for_ds_ready(ds=sandbox_validator_ds, expected=len(gpu_nodes))
    wait_for_ds_ready(ds=vgpu_device_manager_ds, expected=len(nodes_with_supported_gpus))
