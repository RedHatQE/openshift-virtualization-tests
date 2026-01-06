"""
vGPU with RHEL VM
"""

import logging

import pytest
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.template import Template

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from tests.utils import get_resource_by_name
from tests.virt.node.gpu.constants import (
    MDEV_AVAILABLE_INSTANCES_STR,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.node.gpu.utils import (
    verify_gpu_expected_count_updated_on_node,
)
from tests.virt.utils import (
    build_node_affinity_dict,
    get_num_gpu_devices_in_rhel_vm,
    verify_gpu_device_exists_in_vm,
    verify_gpu_device_exists_on_node,
)
from utilities.infra import get_daemonsets
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    running_vm,
    vm_instance_from_template,
)

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.special_infra,
    pytest.mark.gpu,
    pytest.mark.usefixtures("non_existent_mdev_bus_mig_nodes"),
]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestVGPURHELGPUSSpec"


class GpuClusterPolicy(Resource):
    api_group = "nvidia.com"
    api_version = "v1"
    kind = "ClusterPolicy"


@pytest.fixture(scope="class", autouse=True)
def update_cluster_policy_to_enable_mig_vgpu():
    cluster_policy = get_resource_by_name(
        resource_kind=GpuClusterPolicy,
        name="gpu-cluster-policy",
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


@pytest.fixture(scope="class", autouse=True)
def update_daemon_set_to_enable_mig_vgpu(admin_client):
    all_daemonsets = get_daemonsets(admin_client=admin_client, namespace="nvidia-gpu-operator")
    for ds in all_daemonsets:
        if ds.name.startswith("nvidia-vgpu-manager-daemonset"):
            container = ds.instance.spec.template.spec.containers[0]
            c_name = container.name
            c_image = container.image
            patch_data = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": c_name,
                                    "image": c_image,
                                    "imagePullPolicy": "Always",
                                }
                            ]
                        }
                    }
                }
            }
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
    """
    VM Fixture for second VM for vGPU based Tests.
    """
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


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, mig_gpu_vma",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "rhel-vgpu-gpus-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_device": VGPU_DEVICE_NAME_STR,
            },
        ),
    ],
    indirect=True,
)
class TestMIGVGPURHELGPUSSpec:
    @pytest.mark.polarion("CNV-12572")
    def test_permitted_hostdevices_mig_vgpu_visible(
        self,
        update_cluster_policy_to_enable_mig_vgpu,
        update_daemon_set_to_enable_mig_vgpu,
        nodes_with_supported_mig_gpus,
        supported_mig_gpu_device,
        hco_cr_mig_configuration,
        gpu_nodes_labeled_with_mig_vgpu,
        mig_gpu_vma,
    ):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section of the GPU Node.
        """
        vgpu_device_name = supported_mig_gpu_device[VGPU_DEVICE_NAME_STR]
        verify_gpu_device_exists_on_node(gpu_nodes=nodes_with_supported_mig_gpus, device_name=vgpu_device_name)
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=nodes_with_supported_mig_gpus,
            device_name=vgpu_device_name,
            expected_count=supported_mig_gpu_device[MDEV_AVAILABLE_INSTANCES_STR],
        )

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_access_mig_vgpus_rhel_vm")
    @pytest.mark.polarion("CNV-12573")
    def test_access_mig_vgpus_rhel_vm(self, supported_mig_gpu_device, mig_gpu_vma):
        """
        Test vGPU is accessible in VM with GPUs spec.
        """
        verify_gpu_device_exists_in_vm(vm=mig_gpu_vma, supported_gpu_device=supported_mig_gpu_device)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_access_mig_vgpus_rhel_vm"])
    @pytest.mark.polarion("CNV-12574")
    def test_access_vgpus_in_both_rhel_vm_using_same_mig_gpu(self, mig_gpu_vma, mig_gpu_vmb):
        """
        Test vGPU is accessible in both the RHEL VMs, using same GPU, using GPUs spec.
        """
        vm_with_no_gpu = [
            vm.name for vm in [mig_gpu_vma, mig_gpu_vmb] if not get_num_gpu_devices_in_rhel_vm(vm=vm) == 1
        ]
        assert not vm_with_no_gpu, f"GPU does not exist in following vms: {vm_with_no_gpu}"
