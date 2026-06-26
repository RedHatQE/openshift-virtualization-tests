import pytest

from libs.vm.factory import base_vmspec, fedora_vm
from utilities.constants import AMD_64, ARM_64


@pytest.fixture(scope="class")
def arm_vm(namespace, unprivileged_client):
    spec = base_vmspec()
    spec.template.spec.architecture = ARM_64
    vm = fedora_vm(namespace=namespace.name, name="arm-vm", client=unprivileged_client, spec=spec)
    with vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def amd_vm(namespace, unprivileged_client):
    spec = base_vmspec()
    spec.template.spec.architecture = AMD_64
    vm = fedora_vm(namespace=namespace.name, name="amd-vm", client=unprivileged_client, spec=spec)
    with vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
