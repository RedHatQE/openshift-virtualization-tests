"""
GPU PCI Passthrough and vGPU Testing
"""

import pytest

from tests.virt.node.gpu.utils import install_nvidia_drivers_on_windows_vm
from tests.virt.utils import build_node_affinity_dict
from utilities.constants import OS_FLAVOR_WINDOWS
from utilities.virt import vm_instance_from_template


@pytest.fixture(scope="class")
def gpu_vma(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
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
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        vm_affinity=build_node_affinity_dict(values=[nodes_with_supported_gpus[0].name]),
        host_device_name=supported_gpu_device.get(params.get("host_device")),
        gpu_name=supported_gpu_device.get(params.get("gpu_device")),
    ) as gpu_vm:
        if gpu_vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
            install_nvidia_drivers_on_windows_vm(vm=gpu_vm, supported_gpu_device=supported_gpu_device)
        yield gpu_vm
