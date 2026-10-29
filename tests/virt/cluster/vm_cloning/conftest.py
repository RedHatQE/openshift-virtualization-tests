import pytest
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from utilities.architecture import get_multiarch_cpu_arch
from utilities.constants import Images
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import (
    RHEL9_PREFERENCE,
    RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
    U1_SMALL,
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
    # RHEL9_PREFERENCE ("rhel.9") carries preferredArchitecture=amd64 and EFI+SecureBoot,
    # so it cannot schedule on s390x/arm64 nodes. On non-amd64 hetero clusters use the
    # arch-specific preference (e.g. "rhel.10.s390x", "rhel.10.arm64") which sets the
    # correct preferredArchitecture and has no EFI/SMM constraints.
    cpu_arch = get_multiarch_cpu_arch()
    if cpu_arch and cpu_arch != "amd64":
        # Use the arch-specific rhel.10 preference (rhel.9.s390x does not exist upstream)
        preference_name = f"rhel.10.{cpu_arch}"
        image = Images.Rhel.RHEL10_REGISTRY_GUEST_IMG
    else:
        preference_name = RHEL9_PREFERENCE
        image = Images.Rhel.RHEL9_REGISTRY_GUEST_IMG
    with VirtualMachineForCloning(
        name=RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
        image=image,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name=preference_name),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def cloning_job_scope_function(request, unprivileged_client, namespace):
    with create_vm_cloning_job(
        name=f"clone-job-{request.param['source_name']}",
        client=unprivileged_client,
        namespace=namespace.name,
        source_name=request.param["source_name"],
        label_filters=request.param.get("label_filters"),
        annotation_filters=request.param.get("annotation_filters"),
        volume_name_policy=request.param.get("volume_name_policy"),
        target_name=request.param.get("target_name"),
    ) as vmc:
        yield vmc


@pytest.fixture()
def target_vm_scope_function(unprivileged_client, cloning_job_scope_function):
    with target_vm_from_cloning_job(client=unprivileged_client, cloning_job=cloning_job_scope_function) as target_vm:
        yield target_vm
