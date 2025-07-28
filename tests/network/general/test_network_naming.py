import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture()
def invalid_network_names():
    networks = interfaces = ["sec.net"]
    vm_networks = dict(zip(interfaces, networks))
    return {"networks": vm_networks, "interfaces": interfaces}


@pytest.mark.polarion("CNV-8304")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_vm_with_illegal_network_name(namespace, unprivileged_client, invalid_network_names):
    vm_name = "unsupported-network-name-vm"

    with pytest.raises(
        UnprocessibleEntityError,
        match="r.*Network interface name can only contain alphabetical characters*",
    ):
        with VirtualMachineForTests(
            namespace=namespace.name,
            name=vm_name,
            body=fedora_vm_body(name=vm_name),
            client=unprivileged_client,
            **invalid_network_names,
        ):
            return
