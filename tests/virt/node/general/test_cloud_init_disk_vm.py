import pytest

from utilities.constants import CLOUD_INIT_NO_CLOUD
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture()
def vm_with_cloud_init_disk(namespace):
    name = "vm-with-cloud-init-disk"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_type=CLOUD_INIT_NO_CLOUD,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.mark.polarion("CNV-10555")
def test_vm_with_cloud_init_disk_logging_no_disk_capacity(vm_with_cloud_init_disk):
    assert "No disk capacity" not in vm_with_cloud_init_disk.vmi.virt_launcher_pod.log(container="compute"), (
        "Error msg 'No disk capacity' logged in virt-launcher pod"
    )
