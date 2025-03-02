"""
GPU PCI Passthrough and vGPU Testing
"""

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from tests.virt.node.gpu.constants import GPU_CARDS_MAP
from tests.virt.node.gpu.utils import get_nodes_gpu_info, install_nvidia_drivers_on_windows_vm
from utilities.constants import OS_FLAVOR_WINDOWS
from utilities.infra import get_node_selector_dict
from utilities.storage import create_or_update_data_source
from utilities.virt import vm_instance_from_template


@pytest.fixture(scope="session")
def nodes_with_supported_gpus(gpu_nodes, workers_utility_pods):
    gpu_nodes_copy = gpu_nodes.copy()
    for node in gpu_nodes:
        # Currently A30/A100 GPU is unsupported by CNV (required driver not supported)
        if "A30" in get_nodes_gpu_info(util_pods=workers_utility_pods, node=node):
            gpu_nodes_copy.remove(node)
    return gpu_nodes_copy


@pytest.fixture(scope="session")
def fail_if_no_gpu(gpu_nodes, nodes_with_supported_gpus):
    if not gpu_nodes:
        pytest.fail(reason="No gpu nodes found on cluster!")
    if not nodes_with_supported_gpus:
        pytest.skip("No supported gpu nodes found on cluster!")
    elif len(gpu_nodes) < 2:
        pytest.fail(reason="Test needs cluster with atleast two gpu nodes")


@pytest.fixture(scope="session")
def supported_gpu_device(workers_utility_pods, nodes_with_supported_gpus):
    gpu_info = get_nodes_gpu_info(util_pods=workers_utility_pods, node=nodes_with_supported_gpus[0])
    for gpu_id in GPU_CARDS_MAP:
        if gpu_id in gpu_info:
            return GPU_CARDS_MAP[gpu_id]

    raise ResourceNotFoundError("GPU device ID not in current GPU_CARDS_MAP!")


@pytest.fixture(scope="class")
def golden_image_dv_scope_module_data_source_scope_class(admin_client, golden_image_data_volume_scope_module):
    yield from create_or_update_data_source(admin_client=admin_client, dv=golden_image_data_volume_scope_module)


@pytest.fixture(scope="class")
def gpu_vma(
    request,
    unprivileged_client,
    namespace,
    golden_image_dv_scope_module_data_source_scope_class,
    supported_gpu_device,
    nodes_with_supported_gpus,
):
    """
    VM Fixture for both GPU Passthrough and vGPU based Tests.
    """
    params = request.param
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_dv_scope_module_data_source_scope_class,
        node_selector=get_node_selector_dict(node_selector=nodes_with_supported_gpus[0].name),
        host_device_name=supported_gpu_device.get(params.get("host_device")),
        gpu_name=supported_gpu_device.get(params.get("gpu_device")),
    ) as gpu_vm:
        if gpu_vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
            install_nvidia_drivers_on_windows_vm(vm=gpu_vm, supported_gpu_device=supported_gpu_device)
        yield gpu_vm
