"""
GPU PCI Passthrough and vGPU Testing
"""

import pytest

from tests.virt.node.gpu.utils import install_nvidia_drivers_on_windows_vm
from utilities.constants import OS_FLAVOR_WINDOWS
from utilities.infra import get_node_selector_dict
from utilities.storage import create_or_update_data_source
from utilities.virt import vm_instance_from_template


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
