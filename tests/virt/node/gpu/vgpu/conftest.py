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
    NVIDIA_SANDBOX_VALIDATOR_DS,
    VGPU_CONFIG_LABEL,
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
def sandbox_validator_pods_before_grid_relabel(admin_client, nodes_with_supported_gpus):
    """Capture sandbox-validator pod names on node[1] before grid vgpu.config labeling."""
    node = nodes_with_supported_gpus[1]
    old_pod_names = {
        pod.name
        for pod in Pod.get(client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
        if NVIDIA_SANDBOX_VALIDATOR_DS in pod.name and pod.node.name == node.name
    }
    LOGGER.info(f"Captured {NVIDIA_SANDBOX_VALIDATOR_DS} pods on {node.name} before grid relabel: {old_pod_names}")
    return old_pod_names


@pytest.fixture(scope="class")
def node_labeled_with_grid_vgpu_config(
    nodes_with_supported_gpus, supported_gpu_device, sandbox_validator_pods_before_grid_relabel
):
    """Label node[1] with the grid vgpu.config (e.g. A2-4Q)."""
    yield from label_nodes(
        nodes=[nodes_with_supported_gpus[1]],
        labels={VGPU_CONFIG_LABEL: supported_gpu_device[MDEV_GRID_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="class")
def ready_node_with_grid_vgpu_config(
    admin_client,
    node_labeled_with_grid_vgpu_config,
    sandbox_validator_pods_before_grid_relabel,
):
    """Wait for sandbox-validator pod on the relabeled node to restart."""
    node = node_labeled_with_grid_vgpu_config[0]
    old_pod_names = sandbox_validator_pods_before_grid_relabel

    LOGGER.info(f"Waiting for new {NVIDIA_SANDBOX_VALIDATOR_DS} pod on {node.name} (replacing {old_pod_names})")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_10SEC,
        func=lambda: [
            pod
            for pod in Pod.get(client=admin_client, namespace=NamespacesNames.NVIDIA_GPU_OPERATOR)
            if NVIDIA_SANDBOX_VALIDATOR_DS in pod.name
            and pod.node.name == node.name
            and pod.status == Pod.Status.RUNNING
            and pod.name not in old_pod_names
        ],
    ):
        if sample:
            break
    yield


@pytest.fixture(scope="class")
def hco_cr_with_node_specific_mdev_permitted_hostdevices(
    hyperconverged_resource_scope_class,
    supported_gpu_device,
    ready_node_with_grid_vgpu_config,
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
