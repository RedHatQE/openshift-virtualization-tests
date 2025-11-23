import pytest
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

COMMON_INSTANCETYPE_SELECTOR = f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor=redhat.com"


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
