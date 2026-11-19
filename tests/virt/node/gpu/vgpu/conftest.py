"""
vGPU VM
"""

import logging
from contextlib import ExitStack

import pytest
from ocp_resources.cluster_policy import GPUClusterPolicy
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template

from tests.os_params import RHEL_LATEST_LABELS
from tests.virt.node.gpu.constants import (
    GPU_CARDS_MAP,
    GPU_CLUSTER_POLICY_NAME,
    GPU_WORKLOAD_CONFIG_LABEL,
    MDEV_AVAILABLE_INSTANCES_STR,
    MDEV_GRID_NAME_STR,
    MDEV_NAME_STR,
    MIG_VGPU_MANAGER_IMAGE,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
    VGPU_GRID_NAME_STR,
)
from tests.virt.node.gpu.utils import (
    verify_mdev_bus_available,
    vgpu_node_labels_applied,
    wait_for_ds_ready,
    wait_for_gpu_resource_count,
    wait_for_nvidia_vgpu_manager,
)
from tests.virt.utils import patch_hco_cr_with_mdev_permitted_hostdevices
from utilities.exceptions import UnsupportedGPUDeviceError
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_data_volume_template_dict_with_default_storage_class,
    get_nodes_gpu_info,
    running_vm,
    vm_instance_from_template,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def hco_cr_with_mdev_permitted_hostdevices(admin_client, hyperconverged_resource_scope_class, supported_gpu_device):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        admin_client=admin_client,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        supported_gpu_device=supported_gpu_device,
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
def hco_cr_with_node_specific_vgpu_permitted_hostdevices(
    admin_client,
    hyperconverged_resource_scope_class,
    supported_gpu_device,
    ready_node_with_grid_vgpu_config,
):
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "virtualization": {
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
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="package")
def hco_with_disable_mdev_configuration(admin_client, hyperconverged_resource_scope_session):
    """
    Disable HCO automatic mediated-device configuration.

    This fixture must run before any vGPU node labeling to ensure CNV
    does not configure mediated devices (vGPU configuration is handled
    by NVIDIA GPU Operator).
    """
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource_scope_session: {
                "spec": {
                    "virtualization": {
                        "mediatedDevicesConfiguration": {"enabled": False},
                    }
                }
            }
        },
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


@pytest.fixture(scope="module")
def nodes_with_supported_mig_gpus(gpu_nodes, workers_utility_pods):
    """NVIDIA A30 nodes that can expose MIG-backed vGPU devices."""
    mig_gpu_nodes = [
        node for node in gpu_nodes if "A30" in get_nodes_gpu_info(util_pods=workers_utility_pods, node=node)
    ]
    if not mig_gpu_nodes:
        raise UnsupportedGPUDeviceError("No NVIDIA A30 GPU nodes found for MIG vGPU")
    return mig_gpu_nodes


@pytest.fixture(scope="module")
def supported_mig_gpu_device(workers_utility_pods, nodes_with_supported_mig_gpus):
    gpu_info = get_nodes_gpu_info(util_pods=workers_utility_pods, node=nodes_with_supported_mig_gpus[0])
    for gpu_id in GPU_CARDS_MAP:
        if gpu_id in gpu_info:
            return GPU_CARDS_MAP[gpu_id]
    raise UnsupportedGPUDeviceError("GPU device ID not in current GPU_CARDS_MAP!")


@pytest.fixture(scope="module")
def mig_cluster_policy_with_aie_vgpu_manager(admin_client):
    """GPU ClusterPolicy pinned to the AIE vGPU manager image that supports MIG-backed vGPU."""
    cluster_policy = GPUClusterPolicy(
        client=admin_client,
        name=GPU_CLUSTER_POLICY_NAME,
        ensure_exists=True,
    )
    LOGGER.info(f"Set {cluster_policy.name} vgpuManager image to {MIG_VGPU_MANAGER_IMAGE}")
    with ResourceEditor(
        patches={cluster_policy: {"spec": {"vgpuManager": {"image": MIG_VGPU_MANAGER_IMAGE}}}},
    ):
        yield cluster_policy


@pytest.fixture(scope="module")
def mig_vgpu_manager_always_pull_daemonset(nvidia_vgpu_manager_ds, mig_cluster_policy_with_aie_vgpu_manager):
    """nvidia-vgpu-manager DaemonSet pods always pull the MIG-capable image."""
    containers = []
    for container in nvidia_vgpu_manager_ds.instance.spec.template.spec.containers:
        container_patch = dict(container.items())
        container_patch["imagePullPolicy"] = "Always"
        containers.append(container_patch)
    LOGGER.info(f"Set {nvidia_vgpu_manager_ds.name} imagePullPolicy to Always")
    with ResourceEditor(
        patches={nvidia_vgpu_manager_ds: {"spec": {"template": {"spec": {"containers": containers}}}}},
    ):
        yield nvidia_vgpu_manager_ds


@pytest.fixture(scope="module")
def mig_gpu_nodes_labeled_with_vgpu_config(
    hco_with_disable_mdev_configuration,
    nodes_with_supported_mig_gpus,
    supported_mig_gpu_device,
    mig_vgpu_manager_always_pull_daemonset,
):
    yield from label_nodes(
        nodes=nodes_with_supported_mig_gpus,
        labels={VGPU_CONFIG_LABEL: supported_mig_gpu_device[MDEV_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="module")
def mig_gpu_nodes_labeled_with_vm_vgpu(nodes_with_supported_mig_gpus, mig_gpu_nodes_labeled_with_vgpu_config):
    yield from label_nodes(
        nodes=nodes_with_supported_mig_gpus,
        labels={GPU_WORKLOAD_CONFIG_LABEL: "vm-vgpu"},
    )


@pytest.fixture(scope="module")
def mig_nvidia_vgpu_manager_ready(nvidia_vgpu_manager_ds, mig_gpu_nodes_labeled_with_vm_vgpu):
    """Wait until nvidia-vgpu-manager is ready on the MIG vGPU nodes."""
    wait_for_nvidia_vgpu_manager(
        nvidia_vgpu_manager_ds=nvidia_vgpu_manager_ds,
        nodes_with_supported_gpus=mig_gpu_nodes_labeled_with_vm_vgpu,
    )
    yield nvidia_vgpu_manager_ds


@pytest.fixture(scope="module")
def mig_vgpu_ready_nodes(
    gpu_nodes,
    nodes_with_supported_mig_gpus,
    mig_gpu_nodes_labeled_with_vm_vgpu,
    mig_nvidia_vgpu_manager_ready,
    nvidia_sandbox_validator_ds,
    nvidia_vgpu_device_manager_ds,
):
    with vgpu_node_labels_applied(
        gpu_nodes=gpu_nodes,
        nodes_with_supported_gpus=nodes_with_supported_mig_gpus,
        labeled_nodes=mig_gpu_nodes_labeled_with_vm_vgpu,
        sandbox_validator_ds=nvidia_sandbox_validator_ds,
        vgpu_device_manager_ds=nvidia_vgpu_device_manager_ds,
    ) as ready_nodes:
        yield ready_nodes


@pytest.fixture(scope="module")
def mig_mdev_bus_nodes(workers_utility_pods, mig_vgpu_ready_nodes):
    """Verify mdev_bus is available on the MIG vGPU nodes."""
    verify_mdev_bus_available(workers_utility_pods=workers_utility_pods, vgpu_nodes=mig_vgpu_ready_nodes)
    yield mig_vgpu_ready_nodes


@pytest.fixture(scope="module")
def hco_cr_with_mig_mdev_permitted_hostdevices(
    admin_client,
    hyperconverged_resource_scope_module,
    supported_mig_gpu_device,
    mig_mdev_bus_nodes,
):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        admin_client=admin_client,
        hyperconverged_resource=hyperconverged_resource_scope_module,
        supported_gpu_device=supported_mig_gpu_device,
    )


@pytest.fixture()
def mig_gpu_nodes_with_full_mig_vgpu_capacity(nodes_with_supported_mig_gpus, supported_mig_gpu_device):
    """MIG GPU nodes once every configured MIG vGPU instance is free."""
    wait_for_gpu_resource_count(
        gpu_nodes=nodes_with_supported_mig_gpus,
        device_name=supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
        expected_count=supported_mig_gpu_device[MDEV_AVAILABLE_INSTANCES_STR],
    )
    yield nodes_with_supported_mig_gpus


@pytest.fixture()
def mig_gpu_vma(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
    supported_mig_gpu_device,
):
    """RHEL VM requesting one MIG vGPU device on the MIG-configured GPU node."""
    params = request.param
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        gpu_name=supported_mig_gpu_device[params["gpu_device"]],
    ) as mig_gpu_vm:
        yield mig_gpu_vm


@pytest.fixture()
def mig_gpu_vmb(
    unprivileged_client,
    namespace,
    golden_image_data_source_for_test_scope_class,
    supported_mig_gpu_device,
    mig_gpu_vma,
):
    """Second RHEL VM requesting one MIG vGPU device from the same physical GPU."""
    with VirtualMachineForTestsFromTemplate(
        name="rhel-mig-vgpu-vm2",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=golden_image_data_source_for_test_scope_class,
        ),
        gpu_name=supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
    ) as virtual_machine:
        running_vm(vm=virtual_machine)
        yield virtual_machine


@pytest.fixture()
def mig_vgpu_capacity_consuming_vms(
    unprivileged_client,
    namespace,
    golden_image_data_source_for_test_scope_class,
    supported_mig_gpu_device,
    mig_gpu_nodes_with_full_mig_vgpu_capacity,
):
    """Running RHEL VMs that consume every MIG vGPU instance on the GPU node."""
    instance_count = int(supported_mig_gpu_device[MDEV_AVAILABLE_INSTANCES_STR])
    LOGGER.info(f"Starting {instance_count} VMs to consume every {supported_mig_gpu_device[VGPU_DEVICE_NAME_STR]}")
    with ExitStack() as stack:
        consuming_vms = []
        for index in range(instance_count):
            consuming_vm = stack.enter_context(
                cm=vm_instance_from_template(
                    request={
                        "vm_name": f"rhel-mig-vgpu-consumer-{index}",
                        "template_labels": RHEL_LATEST_LABELS,
                        "ssh": False,
                        "guest_agent": False,
                    },
                    unprivileged_client=unprivileged_client,
                    namespace=namespace,
                    data_volume_template=get_data_volume_template_dict_with_default_storage_class(
                        data_source=golden_image_data_source_for_test_scope_class,
                    ),
                    gpu_name=supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
                )
            )
            consuming_vms.append(consuming_vm)
        yield consuming_vms


@pytest.fixture()
def mig_vgpu_unschedulable_vm(
    unprivileged_client,
    namespace,
    golden_image_data_source_for_test_scope_class,
    supported_mig_gpu_device,
    mig_vgpu_capacity_consuming_vms,
):
    """Halted RHEL VM requesting one MIG vGPU device after every instance is consumed."""
    with vm_instance_from_template(
        request={
            "vm_name": "rhel-mig-vgpu-unschedulable",
            "template_labels": RHEL_LATEST_LABELS,
        },
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=golden_image_data_source_for_test_scope_class,
        ),
        gpu_name=supported_mig_gpu_device[VGPU_DEVICE_NAME_STR],
    ) as unschedulable_vm:
        yield unschedulable_vm
