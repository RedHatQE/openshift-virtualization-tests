import pytest
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from utilities.constants import (
    OS_FLAVOR_RHEL,
    RHEL9_PREFERENCE,
    RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
    U1_SMALL,
    Images,
)
from utilities.virt import (
    VirtualMachineForCloning,
    create_vm_cloning_job,
    fedora_vm_body,
    running_vm,
    target_vm_from_cloning_job,
)


@pytest.fixture(scope="class")
def fedora_vm_for_cloning(request, unprivileged_client, namespace, cpu_for_migration):
    name = request.param["vm_name"]
    with VirtualMachineForCloning(
        name=name,
        client=unprivileged_client,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        vm_labels=request.param.get("labels"),
        vm_annotations=request.param.get("annotations"),
        smbios_serial=request.param.get("smbios_serial"),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture(scope="class")
def rhel_vm_with_instancetype_and_preference_for_cloning(namespace, unprivileged_client):
    with VirtualMachineForCloning(
        name=RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name=RHEL9_PREFERENCE),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def cloning_job_scope_function(request, unprivileged_client, namespace):
    yield from create_vm_cloning_job(
        name=f"clone-job-{request.param['source_name']}",
        client=unprivileged_client,
        namespace=namespace.name,
        source_name=request.param["source_name"],
        label_filters=request.param.get("label_filters"),
        annotation_filters=request.param.get("annotation_filters"),
    )


@pytest.fixture()
def target_vm_scope_function(unprivileged_client, cloning_job_scope_function):
    yield from target_vm_from_cloning_job(client=unprivileged_client, cloning_job=cloning_job_scope_function)
