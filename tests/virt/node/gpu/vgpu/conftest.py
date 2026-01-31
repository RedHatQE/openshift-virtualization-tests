"""
vGPU VM
"""

import time

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
from utilities.constants import TIMEOUT_1MIN
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(hyperconverged_resource_scope_class, supported_gpu_device):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        hyperconverged_resource=hyperconverged_resource_scope_class,
        supported_gpu_device=supported_gpu_device,
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


@pytest.fixture(scope="class")
def gpu_nodes_labeled_with_mig_vgpu(nodes_with_supported_mig_gpus):
    labeling_node = label_nodes(
        nodes=nodes_with_supported_mig_gpus,
        labels={"nvidia.com/vgpu.config": "A30-1-6C"},
    )
    labeled_node = next(labeling_node)

    time.sleep(TIMEOUT_1MIN)
    yield labeled_node


@pytest.fixture(scope="class")
def hco_cr_mig_configuration(
    hyperconverged_resource_scope_class,
    supported_mig_gpu_device,
    nodes_with_supported_mig_gpus,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "externalResourceProvider": True,
                                "mdevNameSelector": supported_mig_gpu_device[MDEV_NAME_STR],
                                "resourceName": supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
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
