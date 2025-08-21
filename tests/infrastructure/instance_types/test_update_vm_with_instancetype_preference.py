import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests


def get_mismatched_fields_list(
    vm_instancetype_dict,
    vm_reference_dict,
    instancetype_object_dict,
    preference_object_dict,
):
    mismatch_list = []
    if vm_instancetype_dict["name"] != instancetype_object_dict["metadata"]["name"]:
        mismatch_list.append(
            f"expected vm instancetype name to be: {instancetype_object_dict['metadata']['name']} "
            f"got {vm_instancetype_dict['name']}"
        )
    if vm_instancetype_dict["kind"] != instancetype_object_dict["kind"]:
        mismatch_list.append(
            f"expected vm instancetype kind to be: {vm_instancetype_dict['kind']} "
            f"got {instancetype_object_dict['kind']}"
        )
    if vm_reference_dict["name"] != preference_object_dict["metadata"]["name"]:
        mismatch_list.append(
            f"expected vm preference name to be: {instancetype_object_dict['metadata']['name']} "
            f"got {vm_instancetype_dict['name']}"
        )
    if vm_reference_dict["kind"] != preference_object_dict["kind"]:
        mismatch_list.append(
            f"expected vm preference kind to be: {vm_instancetype_dict['kind']} got {instancetype_object_dict['kind']}"
        )
    return mismatch_list


@pytest.fixture()
def vm_cluster_instance_type_to_update():
    cluster_instancetype_list = list(
        VirtualMachineClusterInstancetype.get(
            label_selector="instancetype.kubevirt.io/memory=4Gi, instancetype.kubevirt.io/cpu=1"
        )
    )
    assert cluster_instancetype_list, "No cluster instance type found on the cluster"
    return cluster_instancetype_list[0]


@pytest.fixture()
def rhel_9_vm_cluster_preference():
    return VirtualMachineClusterPreference(name="rhel.9")


@pytest.fixture()
def simple_rhel_vm(admin_client, namespace):
    with VirtualMachineForTests(
        client=admin_client,
        name="rhel-vm-with-instance-type",
        namespace=namespace.name,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
    ) as vm:
        yield vm


@pytest.fixture()
def updated_vm_with_instancetype_and_preference(
    simple_rhel_vm, vm_cluster_instance_type_to_update, rhel_9_vm_cluster_preference
):
    spec_dict = {
        "instancetype": {
            "kind": vm_cluster_instance_type_to_update.kind,
            "name": vm_cluster_instance_type_to_update.name,
        },
        "preference": {
            "kind": rhel_9_vm_cluster_preference.kind,
            "name": rhel_9_vm_cluster_preference.name,
        },
        "template": {"spec": {"domain": {"resources": None}}},
    }
    ResourceEditor(patches={simple_rhel_vm: {"spec": spec_dict}}).update()
    return simple_rhel_vm


@pytest.mark.gating
@pytest.mark.polarion("CNV-9680")
@pytest.mark.s390x
def test_add_reference_to_existing_vm(
    updated_vm_with_instancetype_and_preference,
    vm_cluster_instance_type_to_update,
    rhel_9_vm_cluster_preference,
):
    vm_spec = updated_vm_with_instancetype_and_preference.instance.spec
    vm_instancetype_dict = vm_spec["instancetype"]
    vm_preference_dict = vm_spec["preference"]
    mismatch_list = get_mismatched_fields_list(
        vm_instancetype_dict=vm_instancetype_dict,
        vm_reference_dict=vm_preference_dict,
        instancetype_object_dict=vm_cluster_instance_type_to_update.instance.to_dict(),
        preference_object_dict=rhel_9_vm_cluster_preference.instance.to_dict(),
    )
    assert not mismatch_list, f"Some references were not updated in the VM: {mismatch_list}"
