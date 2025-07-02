import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.pod import Pod

from utilities.virt import VirtualMachineForTests, fedora_vm_body

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


@pytest.fixture()
def developer_vm(
    unprivileged_client,
    namespace,
):
    name = "unprivileged-client-test-vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="unprivileged-client-test-vm",
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def vm_virt_launcher_pod(developer_vm, namespace, unprivileged_client):
    return next(
        Pod.get(
            dyn_client=unprivileged_client,
            namespace=namespace.name,
            name=developer_vm.vmi.virt_launcher_pod.instance.metadata.name,
        )
    )


@pytest.mark.polarion("CNV-4897")
@pytest.mark.s390x
def test_unprivileged_client_virt_launcher(unprivileged_client, developer_vm, vm_virt_launcher_pod):
    with pytest.raises(
        ApiException,
        match="Reason: Handshake status 403 Forbidden",
    ):
        vm_virt_launcher_pod.execute(
            command=["virsh", "dumpxml", "1"],
            container="compute",
        )
