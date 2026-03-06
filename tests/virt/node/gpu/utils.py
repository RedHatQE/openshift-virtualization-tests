import logging
import shlex

from ocp_resources.resource import ResourceEditor
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    NVIDIA_SANDBOX_DEVICE_PLUGIN_DS,
    NVIDIA_SANDBOX_VALIDATOR_DS,
    SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.utils import fetch_gpu_device_name_from_vm_instance, verify_gpu_device_exists_in_vm
from utilities.constants import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10SEC,
    TIMEOUT_20SEC,
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


def wait_for_sandbox_ds_on_all_nodes(admin_client, ds_name, desired_pods_number, timeout=TIMEOUT_2MIN):
    """Wait for a sandbox DaemonSet to be running on all GPU nodes.

    Args:
        admin_client (DynamicClient): cluster admin client.
        ds_name (str): DaemonSet name (or substring).
        desired_pods_number (int): expected number of pods/nodes.
        timeout (int): timeout in seconds.

    Raises:
        TimeoutExpiredError: If pods don't reach the expected state within timeout.
    """
    daemonsets_in_namespace = get_daemonsets(admin_client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
    for ds in daemonsets_in_namespace:
        if ds_name in ds.name:
            LOGGER.info(f"Waiting for DaemonSet {ds.name} to schedule {desired_pods_number} pods")
            for sample in TimeoutSampler(
                wait_timeout=timeout,
                sleep=TIMEOUT_10SEC,
                func=lambda: ds.instance.status.desiredNumberScheduled,
            ):
                if sample and sample >= desired_pods_number:
                    break

            ds.wait_until_deployed(timeout=timeout)
            return


def update_node_label(nodes, label, value):
    for node in nodes:
        ResourceEditor(patches={node: {"metadata": {"labels": {label: value}}}}).update(backup_resources=False)


def wait_for_sandbox_device_plugin_label_true(nodes, timeout):
    LOGGER.info(f"Waiting for {SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL}=true on all nodes (timeout={timeout}s)")
    try:
        for sample in TimeoutSampler(
            wait_timeout=timeout,
            sleep=TIMEOUT_5SEC,
            func=lambda: all(node.labels.get(SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL) == "true" for node in nodes),
        ):
            if sample:
                return True
    except TimeoutExpiredError:
        LOGGER.warning(f"{SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL} did not become true within {timeout}s")
        return False


def toggle_vgpu_config_label(nodes, vgpu_config):
    update_node_label(nodes=nodes, label=VGPU_CONFIG_LABEL, value=None)

    # Wait for the vgpu.config label to be removed from all nodes
    LOGGER.info(f"Waiting for {VGPU_CONFIG_LABEL} label to be removed from all nodes")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_20SEC,
        sleep=TIMEOUT_5SEC,
        func=lambda: all(VGPU_CONFIG_LABEL not in node.labels for node in nodes),
    ):
        if sample:
            break

    LOGGER.info(f"Re-applying {VGPU_CONFIG_LABEL}={vgpu_config}")
    update_node_label(nodes=nodes, label=VGPU_CONFIG_LABEL, value=vgpu_config)
    wait_for_sandbox_device_plugin_label_true(nodes=nodes, timeout=TIMEOUT_2MIN)


def wait_for_sandbox_validator_pods(admin_client, nodes, vgpu_config):
    """Wait for NVIDIA_SANDBOX_VALIDATOR_DS pods to be running on all GPU nodes.

    Args:
        admin_client (DynamicClient): cluster admin client.
        nodes (list): list of GPU nodes.
        vgpu_config (str): vGPU config value (e.g. "A2-2Q").
    """
    desired_pods_number = len(nodes)

    try:
        wait_for_sandbox_ds_on_all_nodes(
            admin_client=admin_client,
            ds_name=NVIDIA_SANDBOX_VALIDATOR_DS,
            desired_pods_number=desired_pods_number,
            timeout=TIMEOUT_2MIN,
        )
        return
    except TimeoutExpiredError:
        LOGGER.warning(f"{NVIDIA_SANDBOX_VALIDATOR_DS} pods did not come up in time, checking node labels")

    nodes_with_paused_sandbox_plugin = [
        node for node in nodes if node.labels.get(SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL) == "paused-for-vgpu-change"
    ]
    if not nodes_with_paused_sandbox_plugin:
        raise TimeoutExpiredError(f"{NVIDIA_SANDBOX_VALIDATOR_DS} pods not ready on any node")
    toggle_vgpu_config_label(nodes=nodes, vgpu_config=vgpu_config)
    wait_for_sandbox_ds_on_all_nodes(
        admin_client=admin_client, ds_name=NVIDIA_SANDBOX_VALIDATOR_DS, desired_pods_number=desired_pods_number
    )
    wait_for_sandbox_ds_on_all_nodes(
        admin_client=admin_client, ds_name=NVIDIA_SANDBOX_DEVICE_PLUGIN_DS, desired_pods_number=desired_pods_number
    )
