"""
SR-IOV vGPU with RHEL virtual machines.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

Markers:
    - gpu
    - special_infra
"""

import pytest

__test__ = False


class TestSRIOVVGPURHEL:
    """
    Tests for RHEL virtual machines that consume an SR-IOV vGPU on an RHCOS 10 worker node.

    Preconditions:
        - x86_64 bare-metal cluster with OpenShift Virtualization
        - At least one RHCOS 10 worker node with an Ampere or newer NVIDIA GPU
        - NVIDIA GPU Operator 26.11 with SR-IOV vGPU support has virtual functions configured on
          that worker node
        - OpenShift Virtualization permits virtual machines to request the SR-IOV vGPU device
    """

    @pytest.mark.manual
    def test_sriov_vgpu_resources_advertised_on_node(self):
        """
        Test that the RHCOS 10 GPU worker node advertises SR-IOV vGPU virtual functions for scheduling.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - RHCOS 10 GPU worker node with SR-IOV vGPU virtual functions configured

        Steps:
            1. Read the Capacity and Allocatable sections of the RHCOS 10 GPU worker node

        Expected:
            - Capacity and Allocatable list the SR-IOV vGPU virtual function resource
            - The listed count equals the number of configured SR-IOV vGPU virtual functions
        """

    @pytest.mark.manual
    def test_rhel_vm_requesting_sriov_vgpu_detects_gpu(self):
        """
        Test that a RHEL virtual machine requesting an SR-IOV vGPU reaches Running and the guest
        detects a GPU device.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - RHEL virtual machine configured to request one SR-IOV vGPU virtual function on the
              RHCOS 10 GPU worker node

        Steps:
            1. Start the virtual machine and wait for it to reach Running
            2. Query the guest for GPU devices

        Expected:
            - The virtual machine is "Running", and the guest detects a GPU device
        """

    @pytest.mark.manual
    def test_rhel_vm_stays_pending_when_sriov_vgpu_capacity_is_exhausted(self):
        """
        [NEGATIVE] Test that a RHEL virtual machine requesting an SR-IOV vGPU stays unschedulable
        when no virtual function capacity remains, and scheduling feedback names that cause.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - Running RHEL virtual machines on one RHCOS 10 GPU worker node consume every SR-IOV
              vGPU virtual function on that node
            - Additional RHEL virtual machine, restricted to that same worker node, configured to
              request one SR-IOV vGPU virtual function

        Steps:
            1. Create the additional virtual machine
            2. Observe the virtual machine scheduling state and the scheduling events or messages

        Expected:
            - The additional virtual machine remains "Pending" and unschedulable, and the
              scheduling event or message identifies exhausted SR-IOV vGPU capacity as the cause
        """

    @pytest.mark.manual
    def test_two_rhel_vms_share_one_physical_gpu(self):
        """
        Test that two RHEL virtual machines can each use an SR-IOV vGPU virtual function from the
        same physical GPU at the same time.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - Two RHEL virtual machines, each configured to request one SR-IOV vGPU virtual
              function from the same physical GPU on one RHCOS 10 worker node

        Steps:
            1. Start both virtual machines and wait for both to reach Running
            2. Query the guest of each virtual machine for GPU devices

        Expected:
            - Both virtual machines are "Running" at the same time, and the guest of each
              virtual machine detects its assigned GPU device
        """

    @pytest.mark.manual
    def test_pause_unpause_rhel_vm_with_sriov_vgpu(self):
        """
        Test that a RHEL virtual machine with an SR-IOV vGPU can be paused and unpaused and the
        guest detects the GPU device again.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - Running RHEL virtual machine with an SR-IOV vGPU virtual function assigned, SSH
              connectivity established, and the guest detecting the GPU device

        Steps:
            1. Pause the virtual machine
            2. Unpause the virtual machine
            3. Connect to the virtual machine over SSH and query the guest for the GPU device

        Expected:
            - SSH connectivity is re-established within 2 minutes, and the guest detects the GPU
              device again; device reinitialization is acceptable
        """

    @pytest.mark.manual
    def test_restart_rhel_vm_with_sriov_vgpu(self):
        """
        Test that a RHEL virtual machine with an SR-IOV vGPU still detects the GPU device after
        restart.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - Running RHEL virtual machine with an SR-IOV vGPU virtual function assigned, and the
              guest detecting the GPU device

        Steps:
            1. Restart the virtual machine and wait for it to reach Running
            2. Query the guest for GPU devices

        Expected:
            - The virtual machine is "Running" after restart, and the guest detects the GPU device
        """


class TestMixedRHCOSMDevAndSRIOVVGPU:
    """
    Tests for running mdev vGPU and SR-IOV vGPU at the same time on a mixed RHCOS cluster.

    Markers:
        - mixed_os_nodes

    Preconditions:
        - x86_64 bare-metal cluster with at least one RHCOS 9 worker node and one RHCOS 10 worker
          node
        - The RHCOS 9 worker node has an NVIDIA GPU configured for mdev vGPU
        - The RHCOS 10 worker node has an Ampere or newer NVIDIA GPU, and NVIDIA GPU Operator
          26.11 with SR-IOV vGPU support has virtual functions configured on that node
        - OpenShift Virtualization permits virtual machines to request the mdev vGPU device and
          the SR-IOV vGPU device
    """

    @pytest.mark.manual
    def test_mdev_and_sriov_vgpu_rhel_vms_run_concurrently(self):
        """
        Test that an mdev vGPU virtual machine on an RHCOS 9 node and an SR-IOV vGPU virtual
        machine on an RHCOS 10 node run at the same time, and each guest detects its GPU.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/sriov-vgpu.md

        Preconditions:
            - RHEL virtual machine on the RHCOS 9 GPU worker node, configured to request one mdev
              vGPU
            - RHEL virtual machine on the RHCOS 10 GPU worker node, configured to request one
              SR-IOV vGPU virtual function

        Steps:
            1. Start both virtual machines and wait for both to reach Running
            2. Query the guest of each virtual machine for GPU devices

        Expected:
            - Both virtual machines are "Running" at the same time, and the guest of each
              virtual machine detects its assigned GPU device
        """
