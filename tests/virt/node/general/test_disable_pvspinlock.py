import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture(scope="class")
def vm_for_test_pvspinlock(
    namespace,
    unprivileged_client,
):
    name = "vm-for-pvspinlock-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        pvspinlock_enabled=False,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-6877")
@pytest.mark.x86_64
def test_disable_pvspinlock(vm_for_test_pvspinlock):
    assert vm_for_test_pvspinlock.privileged_vmi.xml_dict["domain"]["features"]["pvspinlock"]["@state"] == "off", (
        "pvspinlock is not disabled in domain xml."
    )
