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
from tests.virt.node.gpu.utils import wait_for_ds_ready
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
def node_labeled_with_grid_vgpu_config(vgpu_ready_nodes, supported_gpu_device):
    """Label node[1] with the grid vgpu.config (e.g. A2-4Q)."""
    yield from label_nodes(
        nodes=[vgpu_ready_nodes[1]],
        labels={VGPU_CONFIG_LABEL: supported_gpu_device[MDEV_GRID_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="class")
def ready_node_with_grid_vgpu_config(nvidia_sandbox_validator_ds, node_labeled_with_grid_vgpu_config, gpu_nodes):
    """Confirm sandbox-validator restarted on node[1] after relabeling."""
    wait_for_ds_ready(ds=nvidia_sandbox_validator_ds, expected=len(gpu_nodes) - 1)
    wait_for_ds_ready(ds=nvidia_sandbox_validator_ds, expected=len(gpu_nodes))


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
