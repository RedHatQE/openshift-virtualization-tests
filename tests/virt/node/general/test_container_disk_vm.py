import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.mark.arm64
@pytest.mark.s390x
@pytest.mark.smoke
@pytest.mark.polarion("CNV-5501")
def test_container_disk_vm(
    namespace,
    unprivileged_client,
):
    name = "container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
