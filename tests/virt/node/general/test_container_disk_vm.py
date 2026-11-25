import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.mark.arm64
@pytest.mark.smoke
def test_container_disk_vm(
    namespace,
    unprivileged_client,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-5015 # <skip-jira-utils-check>
    Polarion: CNV-5501
    """
    name = "container-disk-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
