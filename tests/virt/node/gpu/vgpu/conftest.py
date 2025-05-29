"""
vGPU VM
"""

import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.gpu.constants import (
    MDEV_GRID_NAME_STR,
    MDEV_GRID_TYPE_STR,
    MDEV_NAME_STR,
    MDEV_TYPE_STR,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.utils import patch_hco_cr_with_mdev_permitted_hostdevices
from utilities.hco import ResourceEditorValidateHCOReconcile


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(hyperconverged_resource_scope_class, supported_gpu_device):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        hyperconverged_resource=hyperconverged_resource_scope_class, supported_gpu_device=supported_gpu_device
    )


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
