"""
MIG vGPU with RHEL VM

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md
"""

import logging

import pytest
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from tests.virt.node.gpu.constants import (
    MDEV_AVAILABLE_INSTANCES_STR,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.node.gpu.utils import verify_gpu_expected_count_updated_on_node
from tests.virt.utils import (
    get_num_gpu_devices_in_rhel_vm,
    verify_gpu_device_exists_in_vm,
    verify_gpu_device_exists_on_node,
)

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.gpu,
    pytest.mark.usefixtures("hco_cr_with_mig_mdev_permitted_hostdevices"),
]

LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, mig_gpu_vma",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "rhel-mig-vgpu-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_device": VGPU_DEVICE_NAME_STR,
            },
        ),
    ],
    indirect=True,
)
class TestMIGVGPURHELGPUSSpec:
    """
    Tests for VM MIG vGPU support using RHEL virtual machines.

    Preconditions:
        - GPU node with an NVIDIA MIG-capable GPU (NVIDIA A30), MIG mode enabled, and the
          NVIDIA GPU Operator's vGPU manager configured to expose a MIG-backed vGPU mediated device
        - The NVIDIA GPU Operator's ClusterPolicy is updated to use a AIE vGPU manager image that
          supports MIG-backed vGPU
        - The vGPU manager DaemonSet's pods are configured to always pull their container image,
          so the MIG-capable AIE vGPU manager image takes effect
        - The HCO CR is configured to allow the MIG-backed vGPU mediated device as a host device
    """

    @pytest.mark.polarion("CNV-12572")
    def test_permitted_hostdevices_mig_vgpu_visible(
        self,
        mig_gpu_nodes_with_full_mig_vgpu_capacity,
        supported_mig_gpu_device,
    ):
        """
        Test that the GPU node advertises the MIG vGPU resource after MIG vGPU configuration.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md

        Steps:
            1. Read the Capacity and Allocatable sections of the GPU node

        Expected:
            - GPU node Capacity and Allocatable sections list the MIG vGPU resource
            - The listed MIG vGPU resource count equals the number of configured MIG vGPU
              instances
        """
        vgpu_device_name = supported_mig_gpu_device[VGPU_DEVICE_NAME_STR]
        verify_gpu_device_exists_on_node(
            gpu_nodes=mig_gpu_nodes_with_full_mig_vgpu_capacity,
            device_name=vgpu_device_name,
        )
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=mig_gpu_nodes_with_full_mig_vgpu_capacity,
            device_name=vgpu_device_name,
            expected_count=supported_mig_gpu_device[MDEV_AVAILABLE_INSTANCES_STR],
        )

    @pytest.mark.polarion("CNV-12573")
    def test_access_mig_vgpus_rhel_vm(self, supported_mig_gpu_device, mig_gpu_vma):
        """
        Test that a VM requesting a MIG vGPU device reaches Running state and the guest OS
        detects the GPU.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md

        Preconditions:
            - VM configured to request one MIG vGPU device, scheduled on the MIG-configured GPU node

        Steps:
            1. Start the VM and wait for it to reach Running state
            2. Query the guest OS for GPU devices

        Expected:
            - VM is "Running" and the guest OS reports GPU device matching the
              requested MIG vGPU device
        """
        verify_gpu_device_exists_in_vm(vm=mig_gpu_vma, supported_gpu_device=supported_mig_gpu_device)

    @pytest.mark.polarion("CNV-12574")
    def test_access_vgpus_in_both_rhel_vm_using_same_mig_gpu(self, mig_gpu_vma, mig_gpu_vmb):
        """
        Test that two VMs, each using a MIG vGPU slice from the same physical GPU, run
        concurrently.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md

        Preconditions:
            - Two VMs, each configured to request one MIG vGPU device from the same physical
              GPU, scheduled on the same MIG-configured GPU node

        Steps:
            1. Start both VMs and wait for both to reach Running state
            2. Query the guest OS of each VM for GPU devices

        Expected:
            - Both VMs are "Running" concurrently, and the guest OS of each VM reports exactly
              one GPU device matching the requested MIG vGPU device
        """
        vm_with_no_gpu = [vm.name for vm in [mig_gpu_vma, mig_gpu_vmb] if get_num_gpu_devices_in_rhel_vm(vm=vm) != 1]
        assert not vm_with_no_gpu, f"GPU does not exist in following vms: {vm_with_no_gpu}"

    @pytest.mark.polarion("CNV-16809")
    def test_vm_pending_no_mig_vgpu_capacity_available(
        self,
        mig_vgpu_unschedulable_vm,
        supported_mig_gpu_device,
    ):
        """
        [NEGATIVE] Test that a VM requesting a MIG vGPU device remains unschedulable when no
        MIG vGPU capacity remains on the GPU node.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md

        Preconditions:
            - All MIG vGPU instances on the GPU node already consumed by running VMs
            - Additional VM configured to request one MIG vGPU device, scheduled on the same
              GPU node

        Steps:
            1. Create the additional VM requesting one MIG vGPU device
            2. Wait and observe the VM's scheduling state and associated events or messages

        Expected:
            - VM remains "Pending" and is not scheduled, and the scheduling events or status
              messages reported to the user indicate the MIG vGPU resource is unavailable
        """
        LOGGER.info(f"Starting {mig_vgpu_unschedulable_vm.name} with no MIG vGPU capacity left")
        mig_vgpu_unschedulable_vm.start(wait=False)
        mig_vgpu_unschedulable_vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.PENDING)
        mig_vgpu_unschedulable_vm.wait_for_specific_status(status=VirtualMachine.Status.ERROR_UNSCHEDULABLE)
        mig_vgpu_unschedulable_vm.vmi.wait_for_condition(
            condition="PodScheduled",
            status=VirtualMachine.Condition.Status.FALSE,
            reason="Unschedulable",
            message=f"Insufficient {supported_mig_gpu_device[VGPU_DEVICE_NAME_STR]}",
        )
