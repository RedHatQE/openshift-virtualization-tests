"""
vGPU VM
"""

import pytest
from ocp_resources.kubevirt import KubeVirt
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    MDEV_GRID_NAME_STR,
    MDEV_GRID_TYPE_STR,
    MDEV_NAME_STR,
    MDEV_TYPE_STR,
    NVIDIA_VGPU_MANAGER_DS,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.node.gpu.utils import wait_for_manager_pods_deployed
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod, label_nodes


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vm_vgpu(nodes_with_supported_gpus):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={"nvidia.com/gpu.workload.config": "vm-vgpu"})


@pytest.fixture(scope="session")
def vgpu_ready_nodes(admin_client, gpu_nodes_labeled_with_vm_vgpu):
    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name=NVIDIA_VGPU_MANAGER_DS)
    yield gpu_nodes_labeled_with_vm_vgpu


@pytest.fixture(scope="session")
def non_existent_mdev_bus_nodes(workers_utility_pods, vgpu_ready_nodes):
    """
    Check if the mdev_bus needed for vGPU is availble.

    On the Worker Node on which GPU Device exists, Check if the
    mdev_bus needed for vGPU is availble.
    If it's not available, this means the nvidia-vgpu-manager-daemonset
    Pod might not be in running state in nvidia-gpu-operator namespace.
    """
    desired_bus = "mdev_bus"
    non_existent_mdev_bus_nodes = []
    for node in vgpu_ready_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=TIMEOUT_5SEC,
                func=pod_exec.exec,
                command=f"ls /sys/class | grep {desired_bus} || true",
            ):
                if sample:
                    return
        except TimeoutExpiredError:
            non_existent_mdev_bus_nodes.append(node.name)
    if non_existent_mdev_bus_nodes:
        pytest.fail(
            reason=(
                f"On these nodes: {non_existent_mdev_bus_nodes} {desired_bus} is not available."
                "Ensure that in 'nvidia-gpu-operator' namespace nvidia-vgpu-manager-daemonset Pod is Running."
            )
        )


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(hyperconverged_resource_scope_class, supported_gpu_device):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "mediatedDevicesConfiguration": {"mediatedDeviceTypes": [supported_gpu_device[MDEV_TYPE_STR]]},
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "mdevNameSelector": supported_gpu_device[MDEV_NAME_STR],
                                "resourceName": supported_gpu_device[VGPU_DEVICE_NAME_STR],
                            }
                        ]
                    },
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def hco_cr_with_node_specific_mdev_permitted_hostdevices(
    hyperconverged_resource_scope_class, supported_gpu_device, nodes_with_supported_gpus
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "mediatedDevicesConfiguration": {
                        "mediatedDeviceTypes": [supported_gpu_device[MDEV_TYPE_STR]],
                        "nodeMediatedDeviceTypes": [
                            {
                                "mediatedDeviceTypes": [supported_gpu_device[MDEV_GRID_TYPE_STR]],
                                "nodeSelector": {"kubernetes.io/hostname": nodes_with_supported_gpus[1].name},
                            }
                        ],
                    },
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "mdevNameSelector": supported_gpu_device[MDEV_NAME_STR],
                                "resourceName": supported_gpu_device[VGPU_DEVICE_NAME_STR],
                            },
                            {
                                "mdevNameSelector": supported_gpu_device[MDEV_GRID_NAME_STR],
                                "resourceName": supported_gpu_device[VGPU_GRID_NAME_STR],
                            },
                        ]
                    },
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield
