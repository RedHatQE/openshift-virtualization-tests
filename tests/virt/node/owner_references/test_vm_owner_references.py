"""
Check VM, VMI, POD owner references
"""

import pytest

from tests.virt.utils import wait_for_virt_launcher_pod
from utilities.virt import VirtualMachineForTests, fedora_vm_body

pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def fedora_vm(unprivileged_client, namespace):
    name = "owner-references-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        wait_for_virt_launcher_pod(vmi=vm.vmi)
        yield vm


@pytest.mark.gating
@pytest.mark.polarion("CNV-1275")
def test_owner_references_on_vm(fedora_vm):
    """
    Check the Owner References is fill with right data
    like:
        ownerReferences:
          kind: <kind from custom resource>
          apiVersion: <apiVersion from custom resource>
          uid: <uid from custom resource>
          controller: If True:
                      The reference points to the managing controller(the owner)
                      Garbage Collector's behavior related to the object and its owner.
                      If False:
                      Garbage Collector manages the object as an object without an owner,
                      allows to delete it freely.
    """
    vmi = fedora_vm.vmi
    owner_references_pod = vmi.virt_launcher_pod.instance.metadata.ownerReferences[0]

    owner_references_vmi = vmi.instance.metadata.ownerReferences[0]
    # check pod owner references block
    # kind
    assert owner_references_pod.kind == "VirtualMachineInstance", "Pod owner references kind should be VMI"
    assert owner_references_vmi.kind == "VirtualMachine", "VMI owner references kind should be VM"
    # name (all relate to vm name)
    assert owner_references_vmi.name == fedora_vm.name, "VMI owner references is not VM name"
    assert owner_references_pod.name == owner_references_vmi.name, "Pod and VMI name are not equals"
    # controller
    assert owner_references_pod.controller is True, "Pod controller is not set to True"
    assert owner_references_vmi.controller is True, "VMI controller is not set to True"
