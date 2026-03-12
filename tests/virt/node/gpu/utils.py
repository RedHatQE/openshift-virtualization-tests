import logging
import shlex

from ocp_resources.pod import Pod
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
from utilities.infra import get_daemonset_by_name, get_daemonsets, get_pod_by_name_prefix
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


def get_sandbox_validator_pods(admin_client, nodes):
    """Get sandbox-validator pods on the given nodes.

    Args:
        admin_client (DynamicClient): cluster admin client.
        nodes (list): list of nodes to check.

    Returns:
        list: sandbox-validator pods on the given nodes.
    """
    node_names = {node.name for node in nodes}
    return [
        pod
        for pod in get_pod_by_name_prefix(
            client=admin_client,
            pod_prefix=NVIDIA_SANDBOX_VALIDATOR_DS,
            namespace=NamespacesNames.NVIDIA_GPU_OPERATOR,
            get_all=True,
        )
        if pod.node.name in node_names
    ]


def wait_for_new_sandbox_validator_pods(admin_client, nodes, old_pod_names):
    """Wait for new Running sandbox-validator pods on all given nodes.

    Args:
        admin_client (DynamicClient): cluster admin client.
        nodes (list): list of nodes to wait on.
        old_pod_names (set): pod names captured before the change.
    """
    node_names = {node.name for node in nodes}
    LOGGER.info(f"Waiting for new {NVIDIA_SANDBOX_VALIDATOR_DS} pods on {node_names} (replacing {old_pod_names})")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_10SEC,
        func=get_sandbox_validator_pods,
        admin_client=admin_client,
        nodes=nodes,
    ):
        new_running_nodes = {
            pod.node.name for pod in sample if pod.status == Pod.Status.RUNNING and pod.name not in old_pod_names
        }
        if new_running_nodes == node_names:
            LOGGER.info(f"New {NVIDIA_SANDBOX_VALIDATOR_DS} pods running on all nodes: {node_names}")
            break


def wait_for_sandbox_device_plugin_ds(admin_client):
    """Wait for the sandbox-device-plugin DaemonSet to be deployed.

    Args:
        admin_client (DynamicClient): cluster admin client.
    """
    get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name=NVIDIA_SANDBOX_DEVICE_PLUGIN_DS,
        namespace_name=NamespacesNames.NVIDIA_GPU_OPERATOR,
    ).wait_until_deployed()


def update_node_label(nodes, label, value):
    for node in nodes:
        ResourceEditor(patches={node: {"metadata": {"labels": {label: value}}}}).update(backup_resources=False)


def wait_for_sandbox_device_plugin_label_true(nodes):
    LOGGER.info(f"Waiting for {SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL}=true on all nodes (timeout={TIMEOUT_2MIN}s)")
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: all(node.labels.get(SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL) == "true" for node in nodes),
        ):
            if sample:
                return True
    except TimeoutExpiredError:
        LOGGER.warning(f"{SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL} did not become true within {TIMEOUT_2MIN}s")
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
    wait_for_sandbox_device_plugin_label_true(nodes=nodes)


def wait_for_sandbox_validator_pods(admin_client, nodes, vgpu_config):
    """Wait for new sandbox-validator pods to be running on all GPU nodes.

    Captures existing pod names, then waits for new Running pods on all nodes.
    If pods get stuck in paused-for-vgpu-change, toggles the vgpu.config label
    on affected nodes to recover.

    Args:
        admin_client (DynamicClient): cluster admin client.
        nodes (list): list of GPU nodes.
        vgpu_config (str): vGPU config value (e.g. "A2-2Q").
    """
    old_pod_names = {pod.name for pod in get_sandbox_validator_pods(admin_client=admin_client, nodes=nodes)}
    LOGGER.info(f"Captured existing {NVIDIA_SANDBOX_VALIDATOR_DS} pods: {old_pod_names}")

    try:
        wait_for_new_sandbox_validator_pods(admin_client=admin_client, nodes=nodes, old_pod_names=old_pod_names)
    except TimeoutExpiredError:
        LOGGER.warning(f"{NVIDIA_SANDBOX_VALIDATOR_DS} pods did not come up in time, checking for paused nodes")
        nodes_with_paused_sandbox_plugin = [
            node for node in nodes if node.labels.get(SANDBOX_DEVICE_PLUGIN_DEPLOY_LABEL) == "paused-for-vgpu-change"
        ]
        if nodes_with_paused_sandbox_plugin:
            LOGGER.info(
                f"Toggling vgpu config labels on paused nodes:"
                f" {[node.name for node in nodes_with_paused_sandbox_plugin]}"
            )
            toggle_vgpu_config_label(nodes=nodes_with_paused_sandbox_plugin, vgpu_config=vgpu_config)
        wait_for_new_sandbox_validator_pods(admin_client=admin_client, nodes=nodes, old_pod_names=old_pod_names)

    wait_for_sandbox_device_plugin_ds(admin_client=admin_client)
