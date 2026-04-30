"""
vGPU VM
"""

import logging

import pytest
from ocp_resources.cluster_policy import GPUClusterPolicy
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template

from tests.os_params import RHEL_LATEST_LABELS
from tests.utils import get_resource_by_name
from tests.virt.node.gpu.constants import (
    GPU_CARDS_MAP,
    GPU_WORKLOAD_CONFIG_LABEL,
    MDEV_GRID_NAME_STR,
    MDEV_NAME_STR,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.node.gpu.utils import (
    apply_node_labels,
    assert_mdev_bus_exists_on_nodes,
    wait_for_ds_ready,
)
from tests.virt.utils import build_node_affinity_dict, patch_hco_cr_with_mdev_permitted_hostdevices
from utilities.exceptions import UnsupportedGPUDeviceError
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonsets, label_nodes
from utilities.virt import VirtualMachineForTestsFromTemplate, get_nodes_gpu_info, running_vm, vm_instance_from_template

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


@pytest.fixture(scope="class")
def update_cluster_policy_to_enable_mig_vgpu(admin_client):
    cluster_policy = get_resource_by_name(
        resource_kind=GPUClusterPolicy,
        name="gpu-cluster-policy",
        admin_client=admin_client,
    )
    patch_data = {
        "spec": {
            "vgpuManager": {
                "image": "qe-cnv-tests-ocp-nvidia-aie-vgpu-installer",
            }
        }
    }
    with ResourceEditor(patches={cluster_policy: patch_data}):
        yield


@pytest.fixture(scope="class")
def update_daemon_set_to_enable_mig_vgpu(update_cluster_policy_to_enable_mig_vgpu, admin_client):
    all_daemonsets = get_daemonsets(admin_client=admin_client, namespace="nvidia-gpu-operator")
    for ds in all_daemonsets:
        if ds.name.startswith("nvidia-vgpu-manager-daemonset"):
            container = ds.instance.spec.template.spec.containers[0]

            container_patch = dict(container.items())
            container_patch["imagePullPolicy"] = "Always"
            patch_data = {"spec": {"template": {"spec": {"containers": [container_patch]}}}}
            with ResourceEditor(patches={ds: patch_data}):
                yield


@pytest.fixture(scope="class")
def mig_gpu_vmb(
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
    supported_mig_gpu_device,
    mig_gpu_vma,
):
    """VM Fixture for second VM for MIG vGPU based Tests."""
    with VirtualMachineForTestsFromTemplate(
        name="rhel-vgpu-gpus-spec-vm2",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        vm_affinity=mig_gpu_vma.vm_affinity,
        gpu_name=supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def mig_gpu_vma(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
    hco_cr_mig_configuration,
    supported_mig_gpu_device,
    nodes_with_supported_mig_gpus,
):
    params = request.param
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        vm_affinity=build_node_affinity_dict(values=[nodes_with_supported_mig_gpus[0].name]),
        host_device_name=supported_mig_gpu_device.get(params.get("host_device")),
        gpu_name=supported_mig_gpu_device.get(params.get("gpu_device")),
    ) as mig_gpu_vm:
        yield mig_gpu_vm


@pytest.fixture(scope="class")
def nodes_with_supported_mig_gpus(gpu_nodes, workers_utility_pods):
    gpu_nodes_copy = gpu_nodes.copy()
    for node in gpu_nodes:
        if "A2" in get_nodes_gpu_info(util_pods=workers_utility_pods, node=node):
            gpu_nodes_copy.remove(node)
    return gpu_nodes_copy


@pytest.fixture(scope="class")
def supported_mig_gpu_device(workers_utility_pods, nodes_with_supported_mig_gpus):
    gpu_info = get_nodes_gpu_info(util_pods=workers_utility_pods, node=nodes_with_supported_mig_gpus[0])
    for gpu_id in GPU_CARDS_MAP:
        if gpu_id in gpu_info:
            return GPU_CARDS_MAP[gpu_id]

    raise UnsupportedGPUDeviceError("GPU device ID not in current GPU_CARDS_MAP!")


@pytest.fixture(scope="class")
def hco_cr_mig_configuration(
    hyperconverged_resource_scope_class,
    supported_mig_gpu_device,
    mig_gpu_nodes_labeled_with_vgpu_config,
):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        hyperconverged_resource=hyperconverged_resource_scope_class, supported_gpu_device=supported_mig_gpu_device
    )


@pytest.fixture(scope="class")
def mig_gpu_nodes_labeled_with_vgpu_config(
    nodes_with_supported_mig_gpus,
    mig_gpu_nodes_labeled_with_vm_vgpu,
    nvidia_sandbox_validator_ds,
    gpu_nodes,
):
    label_gen = label_nodes(
        nodes=nodes_with_supported_mig_gpus,
        labels={"nvidia.com/vgpu.config": "A30-1-6C"},
    )

    next(label_gen)
    wait_for_ds_ready(ds=nvidia_sandbox_validator_ds, expected=len(gpu_nodes))
    yield
    try:
        next(label_gen)
    except StopIteration:
        pass


@pytest.fixture(scope="class")
def mig_gpu_nodes_labeled_with_vm_vgpu(
    nodes_with_supported_mig_gpus,
    nvidia_vgpu_manager_ds,
    nvidia_vgpu_device_manager_ds,
    nvidia_sandbox_validator_ds,
    gpu_nodes,
):
    label_gen = label_nodes(nodes=nodes_with_supported_mig_gpus, labels={GPU_WORKLOAD_CONFIG_LABEL: "vm-vgpu"})
    next(label_gen)
    wait_for_ds_ready(ds=nvidia_vgpu_manager_ds, expected=len(nodes_with_supported_mig_gpus))
    wait_for_ds_ready(ds=nvidia_vgpu_device_manager_ds, expected=len(nodes_with_supported_mig_gpus))
    yield
    apply_node_labels(nodes=nodes_with_supported_mig_gpus, labels={"nvidia.com/vgpu.config.state": None})
    try:
        next(label_gen)
    except StopIteration:
        pass


@pytest.fixture(scope="class")
def non_existent_mdev_bus_mig_nodes(
    workers_utility_pods,
    mig_gpu_nodes_labeled_with_vm_vgpu,
    nodes_with_supported_mig_gpus,
):
    """
    Check if the mdev_bus needed for vGPU is available.
    """
    assert_mdev_bus_exists_on_nodes(workers_utility_pods=workers_utility_pods, nodes=nodes_with_supported_mig_gpus)
