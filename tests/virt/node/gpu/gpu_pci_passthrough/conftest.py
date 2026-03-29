"""
GPU PCI Passthrough VM
"""

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    DEVICE_ID_STR,
    GPU_DEVICE_NAME_STR,
    GPU_WORKLOAD_CONFIG_LABEL,
    NVIDIA_VFIO_MANAGER_DS,
)
from tests.virt.node.gpu.utils import wait_for_ds_ready
from utilities.constants import KERNEL_DRIVER, TIMEOUT_1MIN, TIMEOUT_5SEC, NamespacesNames
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes
from utilities.virt import get_nodes_gpu_info


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vm_passthrough(nodes_with_supported_gpus):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={GPU_WORKLOAD_CONFIG_LABEL: "vm-passthrough"})


@pytest.fixture(scope="session")
def nvidia_vfio_manager_ds(admin_client):
    return DaemonSet(
        client=admin_client,
        namespace=NamespacesNames.NVIDIA_GPU_OPERATOR,
        name=NVIDIA_VFIO_MANAGER_DS,
    )


@pytest.fixture(scope="session")
def gpu_passthrough_ready_nodes(nvidia_vfio_manager_ds, gpu_nodes_labeled_with_vm_passthrough, gpu_nodes):
    wait_for_ds_ready(
        ds=nvidia_vfio_manager_ds,
        expected=len(gpu_nodes),
    )
    yield gpu_nodes_labeled_with_vm_passthrough


@pytest.fixture(scope="session")
def fail_if_device_unbound_to_vfiopci_driver(workers_utility_pods, gpu_passthrough_ready_nodes):
    """
    Fail if the Kernel Driver vfio-pci is not in use by the NVIDIA GPU Device.
    """
    device_unbound_nodes = []
    for node in gpu_passthrough_ready_nodes:
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=TIMEOUT_5SEC,
                func=get_nodes_gpu_info,
                util_pods=workers_utility_pods,
                node=node,
            ):
                if sample and KERNEL_DRIVER in sample:
                    break
        except TimeoutExpiredError:
            device_unbound_nodes.append(node.name)
    if device_unbound_nodes:
        pytest.fail(
            reason=(
                f"On these nodes: {device_unbound_nodes} GPU Devices are not bound to the {KERNEL_DRIVER} Driver."
                f"Ensure that in 'nvidia-gpu-operator' namespace nvidia-vfio-manager Pod is Running."
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
