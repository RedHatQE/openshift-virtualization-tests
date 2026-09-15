"""
MIG vGPU with RHEL VM

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/mig-vgpu-stp.md
"""

import pytest

pytestmark = [pytest.mark.gpu, pytest.mark.special_infra]

__test__ = False


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
    def test_permitted_hostdevices_mig_vgpu_visible(self):
        """
        Test that the GPU node advertises the MIG vGPU resource after MIG vGPU configuration.

        Steps:
            1. Read the Capacity and Allocatable sections of the GPU node

        Expected:
            - GPU node Capacity and Allocatable sections list the MIG vGPU resource
            - The listed MIG vGPU resource count equals the number of configured MIG vGPU
              instances
        """

    @pytest.mark.polarion("CNV-12573")
    def test_access_mig_vgpus_rhel_vm(self):
        """
        Test that a VM requesting a MIG vGPU device reaches Running state and the guest OS
        detects the GPU.

        Preconditions:
            - VM configured to request one MIG vGPU device, scheduled on the MIG-configured GPU node

        Steps:
            1. Start the VM and wait for it to reach Running state
            2. Query the guest OS for GPU devices

        Expected:
            - VM is "Running" and the guest OS reports GPU device matching the
              requested MIG vGPU device
        """

    @pytest.mark.polarion("CNV-12574")
    def test_access_vgpus_in_both_rhel_vm_using_same_mig_gpu(self):
        """
        Test that two VMs, each using a MIG vGPU slice from the same physical GPU, run
        concurrently.

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

    @pytest.mark.polarion("CNV-16809")
    def test_vm_pending_no_mig_vgpu_capacity_available(self):
        """
        [NEGATIVE] Test that a VM requesting a MIG vGPU device remains unschedulable when no
        MIG vGPU capacity remains on the GPU node.

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
