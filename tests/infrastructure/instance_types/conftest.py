import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from utilities.constants import OS_FLAVOR_RHEL, RHEL10_PREFERENCE, U1_SMALL
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, restart_vm_wait_for_running_vm, running_vm

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


@pytest.fixture(scope="module")
def u1_small_instancetype(unprivileged_client):
    return VirtualMachineClusterInstancetype(
        client=unprivileged_client,
        name=U1_SMALL,
    )


@pytest.fixture(scope="class")
def hotplug_test_vm(
    namespace,
    unprivileged_client,
    u1_small_instancetype,
    rhel10_data_source_scope_session,
):
    with VirtualMachineForTests(
        name="test-hotplug-config-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=u1_small_instancetype,
        vm_preference=VirtualMachineClusterPreference(
            client=unprivileged_client,
            name=RHEL10_PREFERENCE,
        ),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
        ),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def hco_live_update_scenario(request, hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_class: {"spec": {"liveUpdateConfiguration": request.param}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def vm_restarted_for_hco(hco_live_update_scenario, hotplug_test_vm):
    restart_vm_wait_for_running_vm(vm=hotplug_test_vm)
    return hotplug_test_vm
