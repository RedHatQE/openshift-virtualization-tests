"""
GPU PCI Passthrough VM
"""

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor

from tests.virt.node.gpu.constants import DEVICE_ID_STR, GPU_DEVICE_NAME_STR, NVIDIA_VFIO_MANAGER_DS
from tests.virt.node.gpu.utils import wait_for_manager_pods_deployed
from utilities.constants import KERNEL_DRIVER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes
from utilities.virt import get_nodes_gpu_info


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vm_passthrough(nodes_with_supported_gpus):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={"nvidia.com/gpu.workload.config": "vm-passthrough"})


@pytest.fixture(scope="session")
def gpu_passthrough_ready_nodes(admin_client, gpu_nodes_labeled_with_vm_passthrough):
    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name=NVIDIA_VFIO_MANAGER_DS)
    yield gpu_nodes_labeled_with_vm_passthrough


@pytest.fixture(scope="session")
def fail_if_device_unbound_to_vfiopci_driver(workers_utility_pods, gpu_passthrough_ready_nodes):
    """
    Fail if the Kernel Driver vfio-pci is not in use by the NVIDIA GPU Device.
    """
    device_unbound_nodes = []
    for node in gpu_passthrough_ready_nodes:
        if KERNEL_DRIVER not in get_nodes_gpu_info(util_pods=workers_utility_pods, node=node):
            device_unbound_nodes.append(node.name)
    if device_unbound_nodes:
        pytest.fail(
            reason=(
                f"On these nodes: {device_unbound_nodes} GPU Devices are not bound to the {KERNEL_DRIVER} Driver."
                f"Ensure IOMMU and  {KERNEL_DRIVER} Machine Config is applied."
            )
        )


@pytest.fixture(scope="class")
def hco_cr_with_permitted_hostdevices(hyperconverged_resource_scope_class, supported_gpu_device):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "permittedHostDevices": {
                        "pciHostDevices": [
                            {
                                "pciDeviceSelector": supported_gpu_device[DEVICE_ID_STR],
                                "resourceName": supported_gpu_device[GPU_DEVICE_NAME_STR],
                            }
                        ]
                    }
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_vm_gpus_spec(supported_gpu_device, gpu_vma):
    vm_dict = gpu_vma.instance.to_dict()
    vm_spec_dict = vm_dict["spec"]["template"]["spec"]
    vm_spec_dict["domain"]["devices"].pop("hostDevices", "No key Found")
    ResourceEditor(patches={gpu_vma: vm_dict}, action="replace").update()
    ResourceEditor(
        patches={
            gpu_vma: {
                "spec": {
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {
                                    "gpus": [
                                        {
                                            "deviceName": supported_gpu_device[GPU_DEVICE_NAME_STR],
                                            "name": "gpus",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }
    ).update()
