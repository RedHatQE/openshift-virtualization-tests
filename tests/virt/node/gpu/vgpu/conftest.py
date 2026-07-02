"""
vGPU VM
"""

import logging

import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.gpu.constants import (
    GPU_WORKLOAD_CONFIG_LABEL,
    MDEV_GRID_NAME_STR,
    MDEV_NAME_STR,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.node.gpu.utils import (
    verify_mdev_bus_available,
    vgpu_node_labels_applied,
    wait_for_ds_ready,
    wait_for_nvidia_vgpu_manager,
)
from tests.virt.utils import patch_hco_cr_with_mdev_permitted_hostdevices
from utilities.constants.hco import DISABLE_MDEV_CONFIGURATION, FEATURE_GATES
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


@pytest.fixture(scope="package")
def hco_with_disable_mdev_configuration(hyperconverged_resource_scope_session):
    """
    Enable disableMDevConfiguration feature gate in HCO.

    This fixture must run before any vGPU node labeling to ensure CNV
    does not configure mediated devices (vGPU configuration is handled
    by NVIDIA GPU Operator).
    """
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_session: {"spec": {FEATURE_GATES: {DISABLE_MDEV_CONFIGURATION: True}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="package")
def gpu_nodes_labeled_with_vgpu_config(
    hco_with_disable_mdev_configuration,
    nodes_with_supported_gpus,
    supported_gpu_device,
):
    yield from label_nodes(
        nodes=nodes_with_supported_gpus,
        labels={VGPU_CONFIG_LABEL: supported_gpu_device[MDEV_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="package")
def gpu_nodes_labeled_with_vm_vgpu(nodes_with_supported_gpus, gpu_nodes_labeled_with_vgpu_config):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={GPU_WORKLOAD_CONFIG_LABEL: "vm-vgpu"})


@pytest.fixture(scope="package")
def nvidia_vgpu_manager_ready(
    nvidia_vgpu_manager_ds,
    gpu_nodes_labeled_with_vm_vgpu,
):
    """Wait until nvidia-vgpu-manager DaemonSet is ready on all vGPU nodes."""
    wait_for_nvidia_vgpu_manager(
        nvidia_vgpu_manager_ds=nvidia_vgpu_manager_ds,
        nodes_with_supported_gpus=gpu_nodes_labeled_with_vm_vgpu,
    )
    yield nvidia_vgpu_manager_ds


@pytest.fixture(scope="package")
def vgpu_ready_nodes(
    gpu_nodes,
    nodes_with_supported_gpus,
    gpu_nodes_labeled_with_vm_vgpu,
    nvidia_vgpu_manager_ready,
    nvidia_sandbox_validator_ds,
    nvidia_vgpu_device_manager_ds,
):
    with vgpu_node_labels_applied(
        gpu_nodes=gpu_nodes,
        nodes_with_supported_gpus=nodes_with_supported_gpus,
        labeled_nodes=gpu_nodes_labeled_with_vm_vgpu,
        sandbox_validator_ds=nvidia_sandbox_validator_ds,
        vgpu_device_manager_ds=nvidia_vgpu_device_manager_ds,
    ) as nodes:
        yield nodes


@pytest.fixture(scope="package")
def non_existent_mdev_bus_nodes(workers_utility_pods, vgpu_ready_nodes):
    """Verify mdev_bus is available on all vGPU nodes."""
    verify_mdev_bus_available(workers_utility_pods=workers_utility_pods, vgpu_nodes=vgpu_ready_nodes)
    yield vgpu_ready_nodes
