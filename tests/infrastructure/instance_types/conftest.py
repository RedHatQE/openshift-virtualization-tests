import pytest
from ocp_resources.resource import Resource
from ocp_resources.validating_admission_policy import ValidatingAdmissionPolicy
from ocp_resources.validating_admission_policy_binding import ValidatingAdmissionPolicyBinding
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from tests.infrastructure.instance_types.constants import WINDOWS_DEDICATED_CPU_MESSAGE, WINDOWS_VCPU_OVERCOMMIT_STR
from utilities.constants.images import (
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WIN_CONTAINER_DISK,
)
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
)
from utilities.virt import VirtualMachineForTests

COMMON_INSTANCETYPE_SELECTOR = f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor=redhat.com"
LATEST_WINDOWS_IMAGE_NAMESPACE = "latest-windows-image"


@pytest.fixture(scope="session")
def base_vm_cluster_preferences(unprivileged_client):
    return list(
        VirtualMachineClusterPreference.get(
            client=unprivileged_client,
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


@pytest.fixture(scope="session")
def base_vm_cluster_instancetypes(unprivileged_client):
    return list(
        VirtualMachineClusterInstancetype.get(
            client=unprivileged_client,
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


@pytest.fixture(scope="class")
def windows_validating_admission_policy(admin_client):
    with ValidatingAdmissionPolicy(
        client=admin_client,
        name=WINDOWS_VCPU_OVERCOMMIT_STR,
        failure_policy="Fail",
        match_conditions=[
            {
                "expression": (
                    "(('kubevirt.io/preference-name' in object.metadata.annotations) && "
                    "(object.metadata.annotations['kubevirt.io/preference-name'].lowerAscii().contains('windows'))) || "
                    "(('kubevirt.io/cluster-preference-name' in object.metadata.annotations) && "
                    "(object.metadata.annotations['kubevirt.io/cluster-preference-name']"
                    ".lowerAscii().contains('windows'))) || "
                    "(('vm.kubevirt.io/os' in object.metadata.annotations) && "
                    "(object.metadata.annotations['vm.kubevirt.io/os'].lowerAscii().contains('windows')))"
                ),
                "name": WINDOWS_VCPU_OVERCOMMIT_STR,
            }
        ],
        match_constraints={
            "resourceRules": [
                {
                    "apiGroups": ["kubevirt.io"],
                    "apiVersions": ["*"],
                    "operations": ["CREATE", "UPDATE"],
                    "resources": ["virtualmachineinstances"],
                }
            ]
        },
        validations=[
            {
                "expression": (
                    "has(object.spec.domain.cpu.dedicatedCpuPlacement) && "
                    "object.spec.domain.cpu.dedicatedCpuPlacement == true"
                ),
                "message": WINDOWS_DEDICATED_CPU_MESSAGE,
            }
        ],
    ) as vap:
        yield vap


@pytest.fixture(scope="class")
def windows_validating_admission_policy_binding(admin_client):
    with ValidatingAdmissionPolicyBinding(
        client=admin_client,
        name=f"{WINDOWS_VCPU_OVERCOMMIT_STR}-binding",
        policy_name=WINDOWS_VCPU_OVERCOMMIT_STR,
        validation_actions=["Deny"],
    ) as vapb:
        yield vapb


@pytest.fixture()
def windows_vm_for_dedicated_cpu(
    request, unprivileged_client, namespace, windows_validation_os_images_data_source_scope_session
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=request.param["vm_name"],
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(
            client=unprivileged_client, name=request.param["instance_type_name"]
        ),
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows_validation_os_images_data_source_scope_session,
        ),
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        disk_type=None,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def rhel_vm_for_dedicated_cpu(unprivileged_client, namespace, latest_rhel_data_source):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-d1-vm",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name="d1.large"),
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=latest_rhel_data_source,
        ),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        vm.start()
        yield vm
