"""
Test VM with cloudInit disk.
"""

import pytest

from utilities.constants import CLOUD_INIT_NO_CLOUD
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


@pytest.fixture()
def vm_with_cloud_init_type(namespace):
    """VM with cloudInit disk."""
    name = "vm-cloud-init-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cloud_init_type=CLOUD_INIT_NO_CLOUD,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-3804")
def test_cloud_init_types(vm_with_cloud_init_type):
    vm_with_cloud_init_type.ssh_exec.executor().is_connective()
