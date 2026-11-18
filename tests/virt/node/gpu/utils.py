import logging
import shlex
from collections.abc import Sequence
from contextlib import contextmanager

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.daemonset import DaemonSet
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    SANDBOX_VALIDATOR_DEPLOY_LABEL,
    VGPU_DEVICE_MANAGER_DEPLOY_LABEL,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.utils import (
    fetch_gpu_device_name_from_vm_instance,
    get_non_terminated_pods,
    verify_gpu_device_exists_in_vm,
)
from utilities.constants.timeouts import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
)
from utilities.infra import ExecCommandOnPod
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
        wait_timeout=TIMEOUT_2MIN,
    )
    # Wait for Running VM, as only vGPU VM Reboots after installing NVIDIA GRID Drivers.
    if fetch_gpu_device_name_from_vm_instance(vm=vm) == vgpu_device_name:
        running_vm(vm=vm)


def wait_for_vgpu_manager_container_image_pull_always(daemon_set: DaemonSet) -> None:
    """Wait until nvidia-vgpu-manager-ctr container uses imagePullPolicy Always.

    Args:
        daemon_set: The vGPU manager DaemonSet to check.

    Raises:
        TimeoutExpiredError: The container is not Always before the timeout.
    """
    LOGGER.info(f"Waiting for {daemon_set.name} nvidia-vgpu-manager-ctr imagePullPolicy Always")

    def _vgpu_manager_pull_policy_is_always() -> bool:
        for container in daemon_set.instance.spec.template.spec.containers:
            if container.name == "nvidia-vgpu-manager-ctr":
                return container.imagePullPolicy == "Always"
        return False

    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN, sleep=TIMEOUT_5SEC, func=_vgpu_manager_pull_policy_is_always
    ):
        if sample:
            return


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


@contextmanager
def vgpu_node_labels_applied(
    gpu_nodes,
    nodes_with_supported_gpus,
    labeled_nodes,
    sandbox_validator_ds,
    vgpu_device_manager_ds,
):
    """Cycle vGPU deploy labels and clear vgpu.config.state on teardown.

    Args:
        gpu_nodes: All GPU nodes.
        nodes_with_supported_gpus: vGPU-supported nodes.
        labeled_nodes: Nodes returned to the caller after setup completes.
        sandbox_validator_ds: nvidia-sandbox-validator DaemonSet object.
        vgpu_device_manager_ds: nvidia-vgpu-device-manager DaemonSet object.

    Yields:
        The labeled vGPU nodes after deploy-label cycling completes.
    """
    try:
        toggle_vgpu_deploy_labels(
            gpu_nodes=gpu_nodes,
            nodes_with_supported_gpus=nodes_with_supported_gpus,
            sandbox_validator_ds=sandbox_validator_ds,
            vgpu_device_manager_ds=vgpu_device_manager_ds,
        )
        yield labeled_nodes
    finally:
        apply_node_labels(nodes=labeled_nodes, labels={"nvidia.com/vgpu.config.state": None})


def wait_for_nvidia_vgpu_manager(nvidia_vgpu_manager_ds, nodes_with_supported_gpus):
    """Wait until nvidia-vgpu-manager DaemonSet is ready on all vGPU nodes.

    Args:
        nvidia_vgpu_manager_ds: nvidia-vgpu-manager DaemonSet object.
        nodes_with_supported_gpus: vGPU-supported nodes.
    """
    wait_for_ds_ready(ds=nvidia_vgpu_manager_ds, expected=len(nodes_with_supported_gpus))


def wait_for_mig_vgpu_manager_rollout(
    nvidia_vgpu_manager_ds: DaemonSet,
    mig_gpu_nodes: list[Node],
    image_name: str,
) -> None:
    """Wait until each MIG node has a running vGPU manager pod with the given image.

    Raises:
        TimeoutExpiredError: A selected node does not have that pod before the timeout.
    """
    node_names = {node.name for node in mig_gpu_nodes}
    label_selector = ",".join(
        f"{key}={value}" for key, value in nvidia_vgpu_manager_ds.instance.spec.selector.matchLabels.items()
    )
    LOGGER.info(f"Waiting for {nvidia_vgpu_manager_ds.name} image {image_name} on {sorted(node_names)}")

    def _pods_updated() -> bool:
        ready_nodes = set()
        for pod in Pod.get(
            client=nvidia_vgpu_manager_ds.client,
            namespace=nvidia_vgpu_manager_ds.namespace,
            label_selector=label_selector,
        ):
            if pod.instance.spec.nodeName not in node_names or pod.status != Pod.Status.RUNNING:
                continue
            if any(
                image_name in container.image and container.imagePullPolicy == "Always"
                for container in pod.instance.spec.containers
            ):
                ready_nodes.add(pod.instance.spec.nodeName)
        return ready_nodes == node_names

    for sample in TimeoutSampler(wait_timeout=TIMEOUT_5MIN, sleep=TIMEOUT_5SEC, func=_pods_updated):
        if sample:
            return


def verify_mdev_bus_available(workers_utility_pods, vgpu_nodes):
    """Verify mdev_bus is available on all vGPU nodes.

    Args:
        workers_utility_pods: Utility pods for executing commands on nodes.
        vgpu_nodes: List of vGPU-ready nodes to check.
    """
    desired_bus = "mdev_bus"
    nodes_without_mdev_bus = []
    for node in vgpu_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=TIMEOUT_5SEC,
                func=pod_exec.exec,
                command=f"ls /sys/class | grep {desired_bus} || true",
            ):
                if sample:
                    break
        except TimeoutExpiredError:
            nodes_without_mdev_bus.append(node.name)
    if nodes_without_mdev_bus:
        pytest.fail(
            reason=(
                f"On these nodes: {nodes_without_mdev_bus} mdev_bus is not available. "
                "Ensure that in 'nvidia-gpu-operator' namespace nvidia-vgpu-manager-daemonset Pod is Running."
            )
        )


def gpu_allocated_count(admin_client: DynamicClient, gpu_node: Node, device_name: str) -> int:
    """Return the GPU device requests already placed on a node.

    This is the Requests value under Allocated resources in the node description.

    Args:
        admin_client: Client that can list pods on the node.
        gpu_node: Node whose non-terminated pods are summed.
        device_name: Extended resource name requested by those pods.

    Returns:
        Total requested count of the device on the node.
    """
    allocated = 0
    for pod in get_non_terminated_pods(client=admin_client, node=gpu_node):
        for container in pod.instance.spec.containers:
            if not container.resources or not container.resources.requests:
                continue
            device_request = container.resources.requests.get(device_name)
            if device_request:
                allocated += int(device_request)
    LOGGER.info(f"Allocated {device_name} on {gpu_node.name} is {allocated}")
    return allocated


def wait_for_gpu_resource_count(gpu_nodes: Sequence[Node], device_name: str, expected_count: str) -> None:
    """Wait until capacity and allocatable for a GPU resource match the expected count.

    Args:
        gpu_nodes: GPU nodes to read.
        device_name: Extended resource name advertised by the node.
        expected_count: Resource count expected in both capacity and allocatable.

    Raises:
        TimeoutExpiredError: If the count does not match within TIMEOUT_5MIN.
    """
    LOGGER.info(
        f"Waiting for {device_name} capacity and allocatable to equal {expected_count} "
        f"on {[gpu_node.name for gpu_node in gpu_nodes]}"
    )

    def _resource_count_matches():
        for gpu_node in gpu_nodes:
            for status_type in ("allocatable", "capacity"):
                resources = getattr(gpu_node.instance.status, status_type)
                if device_name not in resources.keys() or resources[device_name] != expected_count:
                    return False
        return True

    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=_resource_count_matches,
    ):
        if sample:
            return
