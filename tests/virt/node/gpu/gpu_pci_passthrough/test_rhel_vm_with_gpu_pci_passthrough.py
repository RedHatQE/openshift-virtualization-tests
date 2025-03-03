"""
GPU PCI Passthrough with RHEL VM
"""

import logging

import pytest
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from tests.virt.node.gpu.constants import GPU_DEVICE_NAME_STR, VGPU_DEVICE_NAME_STR
from tests.virt.node.gpu.utils import (
    restart_and_check_gpu_exists,
    verify_gpu_device_exists_in_vm,
    verify_gpu_device_exists_on_node,
    verify_gpu_expected_count_updated_on_node,
)
from tests.virt.utils import pause_optional_migrate_unpause_and_check_connectivity, running_sleep_in_linux
from utilities.constants import TIMEOUT_5SEC
from utilities.infra import get_node_selector_dict
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.gpu,
    pytest.mark.usefixtures(
        "fail_if_device_unbound_to_vfiopci_driver",
        "hco_cr_with_permitted_hostdevices",
    ),
]

ALLOCATABLE = "allocatable"
TESTS_CLASS_RHEL_HOSTDEVICES_NAME = "TestPCIPassthroughRHELHostDevicesSpec"
TESTS_CLASS_RHEL_GPUS_NAME = "TestPCIPassthroughRHELGPUSSpec"
DATA_VOLUME_DICT = {
    "dv_name": RHEL_LATEST_OS,
    "image": RHEL_LATEST["image_path"],
    "storage_class": py_config["default_storage_class"],
    "dv_size": RHEL_LATEST["dv_size"],
}


LOGGER = logging.getLogger(__name__)


def wait_for_failed_boot_without_permitted_hostdevices(vm, supported_gpu_device):
    """A VM without permitted hostdevices attached should not be able to start."""
    expected_error = (
        f"failed to render launch manifest: HostDevice {supported_gpu_device['vgpu_device_name']} "
        "is not permitted in permittedHostDevices configuration"
    )
    LOGGER.info(f"Starting VM {vm.name} without permitted hostdevices")
    vm.start(wait=False)
    LOGGER.info("Waiting for error condition to appear")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5SEC,
        sleep=1,
        func=lambda: vm.vmi.instance.status.conditions,
    ):
        if sample and any([expected_error in condition.get("message", "") for condition in sample]):
            return True


@pytest.fixture()
def non_permitted_hostdevices_vm(nodes_with_supported_gpus, unprivileged_client, namespace, supported_gpu_device):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="passthrough-non-permitted-hostdevices-vm",
        namespace=namespace.name,
        image=CIRROS_IMAGE,
        node_selector=get_node_selector_dict(node_selector=[*nodes_with_supported_gpus][0].name),
        host_device_name=supported_gpu_device[VGPU_DEVICE_NAME_STR],
        memory_requests="1Gi",
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vma",
    [
        pytest.param(
            DATA_VOLUME_DICT,
            {
                "vm_name": "rhel-passthrough-hostdevices-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "host_device": GPU_DEVICE_NAME_STR,
            },
        ),
    ],
    indirect=True,
)
class TestPCIPassthroughRHELHostDevicesSpec:
    """
    Test PCI Passthrough with RHEL VM using HostDevices Spec.
    """

    @pytest.mark.polarion("CNV-5638")
    def test_permitted_hostdevices_visible(self, gpu_vma, nodes_with_supported_gpus, supported_gpu_device):
        """
        Test Permitted HostDevice is visible and count updated under Capacity/Allocatable
        section of the GPU Node.
        """
        gpu_device_name = supported_gpu_device[GPU_DEVICE_NAME_STR]
        verify_gpu_device_exists_on_node(gpu_nodes=nodes_with_supported_gpus, device_name=gpu_device_name)
        verify_gpu_expected_count_updated_on_node(
            gpu_nodes=nodes_with_supported_gpus, device_name=gpu_device_name, expected_count="1"
        )

    @pytest.mark.dependency(name=f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::test_access_hostdevices_rhel_vm")
    @pytest.mark.polarion("CNV-5639")
    def test_access_hostdevices_rhel_vm(self, supported_gpu_device, gpu_vma):
        """
        Test Device is accessible in VM with hostdevices spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vma, supported_gpu_device=supported_gpu_device)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::test_access_hostdevices_rhel_vm"])
    @pytest.mark.polarion("CNV-5643")
    def test_pause_unpause_hostdevices_rhel_vm(self, gpu_vma):
        """
        Test VM with Device using hostdevices spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vma):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_RHEL_HOSTDEVICES_NAME}::test_access_hostdevices_rhel_vm"])
    @pytest.mark.polarion("CNV-5641")
    def test_restart_hostdevices_rhel_vm(self, gpu_vma, supported_gpu_device):
        """
        Test VM with Device using hostdevices spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module, gpu_vma",
    [
        pytest.param(
            DATA_VOLUME_DICT,
            {
                "vm_name": "rhel-passthrough-gpus-spec-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "gpu_device": GPU_DEVICE_NAME_STR,
            },
        ),
    ],
    indirect=True,
)
class TestPCIPassthroughRHELGPUSSpec:
    """
    Test PCI Passthrough with RHEL VM using GPUS Spec.
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm")
    @pytest.mark.polarion("CNV-5640")
    def test_access_gpus_rhel_vm(self, supported_gpu_device, gpu_vma):
        """
        Test Device is accessible in VM with GPUS spec.
        """
        verify_gpu_device_exists_in_vm(vm=gpu_vma, supported_gpu_device=supported_gpu_device)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm"])
    @pytest.mark.polarion("CNV-5644")
    def test_pause_unpause_gpus_rhel_vm(self, gpu_vma):
        """
        Test VM with Device using GPUS spec, can be paused and unpaused successfully.
        """
        with running_sleep_in_linux(vm=gpu_vma):
            pause_optional_migrate_unpause_and_check_connectivity(vm=gpu_vma)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_RHEL_GPUS_NAME}::access_gpus_rhel_vm"])
    @pytest.mark.polarion("CNV-5642")
    def test_restart_gpus_rhel_vm(self, gpu_vma, supported_gpu_device):
        """
        Test VM with Device using GPUS spec, can be restarted successfully.
        """
        restart_and_check_gpu_exists(vm=gpu_vma, supported_gpu_device=supported_gpu_device)


@pytest.mark.polarion("CNV-5645")
def test_only_permitted_hostdevices_allowed(supported_gpu_device, non_permitted_hostdevices_vm):
    """
    Test that virt-launcher Pod creation is not allowed,
    for devices which are not in Permitted Hostdevices section of HCO CR.

    Permitting GPU_DEVICE_NAME in HCO CR and assigning VGPU_DEVICE_NAME as host_device.
    """
    assert wait_for_failed_boot_without_permitted_hostdevices(
        vm=non_permitted_hostdevices_vm,
        supported_gpu_device=supported_gpu_device,
    ), f"VM started and Virt-launcher Pod creation of VM: {non_permitted_hostdevices_vm.name} is not allowed, "
    "for gpus which are not in Permitted Hostdevices section of HCO CR."
