"""
vGPU VM
"""

import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.pod import Pod
from timeout_sampler import TimeoutSampler

from tests.virt.node.gpu.constants import (
    MDEV_GRID_NAME_STR,
    MDEV_NAME_STR,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.utils import patch_hco_cr_with_mdev_permitted_hostdevices
from utilities.constants import TIMEOUT_2MIN, TIMEOUT_10SEC, NamespacesNames
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(hyperconverged_resource_scope_class, supported_gpu_device):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        hyperconverged_resource=hyperconverged_resource_scope_class, supported_gpu_device=supported_gpu_device
    )


@pytest.fixture(scope="class")
def grid_node_labeled_with_vgpu_config(nodes_with_supported_gpus, supported_gpu_device):
    """Label node[1] with the grid vgpu.config (e.g. A2-4Q)."""
    yield from label_nodes(
        nodes=[nodes_with_supported_gpus[1]],
        labels={"nvidia.com/vgpu.config": supported_gpu_device[MDEV_GRID_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="class")
def grid_node_vgpu_config_ready(admin_client, nodes_with_supported_gpus, grid_node_labeled_with_vgpu_config):
    """Wait for sandbox-validator pod on the relabeled node to restart and become Running."""
    node = nodes_with_supported_gpus[1]
    LOGGER.info(f"Waiting for nvidia-sandbox-validator pod on {node.name} to be Running")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_10SEC,
        func=lambda: [
            pod
            for pod in Pod.get(client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
            if "nvidia-sandbox-validator" in pod.name
            and pod.node.name == node.name
            and pod.status == Pod.Status.RUNNING
        ],
    ):
        if sample:
            break
    yield grid_node_labeled_with_vgpu_config


@pytest.fixture(scope="class")
def hco_cr_with_node_specific_mdev_permitted_hostdevices(
    hyperconverged_resource_scope_class,
    supported_gpu_device,
    grid_node_vgpu_config_ready,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "externalResourceProvider": True,
                                "mdevNameSelector": supported_gpu_device[MDEV_NAME_STR],
                                "resourceName": supported_gpu_device[VGPU_DEVICE_NAME_STR],
                            },
                            {
                                "externalResourceProvider": True,
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
