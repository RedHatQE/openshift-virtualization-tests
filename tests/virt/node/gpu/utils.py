import logging
import shlex

from ocp_resources.pod import Pod
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import VGPU_DEVICE_NAME_STR
from tests.virt.utils import fetch_gpu_device_name_from_vm_instance, verify_gpu_device_exists_in_vm
from utilities.constants import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_10SEC,
    NamespacesNames,
)
from utilities.infra import get_daemonsets
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


def wait_for_manager_pods_deployed(admin_client, ds_name):
    daemonsets_in_namespace = get_daemonsets(admin_client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
    for ds in daemonsets_in_namespace:
        if ds_name in ds.name:
            ds.wait_until_deployed()


def redeploy_vgpu_device_manager_pods(admin_client):
    for pod in Pod.get(client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR):
        if "nvidia-vgpu-device-manager" in pod.name:
            pod.delete(wait=True)
    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name="nvidia-vgpu-device-manager")


def restart_vgpu_device_manager(admin_client, nodes):
    """Workaround for CNV-77535: vgpu-device-manager pods fail to discover vGPU device.

    Waits for vgpu.config.state=success on all GPU nodes. If the state does not reach success
    within the timeout, redeploys nvidia-vgpu-device-manager pods to force a retry.
    On initial setup, the device-manager may start before the NVIDIA driver is fully loaded,
    causing "Driver Not Loaded" errors. Redeploying the pods forces a fresh attempt with
    the driver already loaded.

    Args:
        admin_client (DynamicClient): cluster admin client.
        nodes (list): list of GPU nodes to verify vgpu.config.state label on.
    """

    def _vgpu_config_succeeded():
        vgpu_config_state_label = "nvidia.com/vgpu.config.state"
        return all(node.labels.get(vgpu_config_state_label) == "success" for node in nodes)

    LOGGER.info("Waiting for vgpu.config.state=success, redeploying device-manager if needed")
    for attempt in range(3):
        try:
            for sample in TimeoutSampler(wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_10SEC, func=_vgpu_config_succeeded):
                if sample:
                    break
        except TimeoutExpiredError:
            LOGGER.warning(f"vgpu.config.state not success after attempt {attempt + 1}, redeploying device-manager")
            redeploy_vgpu_device_manager_pods(admin_client=admin_client)
            continue
        break
    else:
        raise TimeoutExpiredError("Timed out waiting for vgpu.config.state=success after 3 attempts")

    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name="nvidia-sandbox-device-plugin-daemonset")
    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name="nvidia-sandbox-validator")
