"""
vGPU VM
"""

import logging

import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.gpu.constants import (
    MDEV_GRID_NAME_STR,
    MDEV_NAME_STR,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.node.gpu.utils import get_sandbox_validator_pods, wait_for_new_sandbox_validator_pods
from tests.virt.utils import patch_hco_cr_with_mdev_permitted_hostdevices
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
    return {
        pod.name for pod in get_sandbox_validator_pods(admin_client=admin_client, nodes=[nodes_with_supported_gpus[1]])
    }


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
    sandbox_validator_pods_before_grid_relabel,
    node_labeled_with_grid_vgpu_config,
):
    """Wait for sandbox-validator pod on the relabeled node to restart."""
    wait_for_new_sandbox_validator_pods(
        admin_client=admin_client,
        nodes=node_labeled_with_grid_vgpu_config,
        old_pod_names=sandbox_validator_pods_before_grid_relabel,
    )
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
