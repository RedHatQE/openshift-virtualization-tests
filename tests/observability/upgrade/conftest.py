import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities.infra import create_ns, get_node_selector_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture(scope="session")
def vm_with_node_selector_for_upgrade(namespace_for_outdated_vm_upgrade, unprivileged_client, worker_node1):
    name = "vm-with-node-selector"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace_for_outdated_vm_upgrade.name,
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def outdated_vmis_count(admin_client):
    vmis_with_outdated_label = len(
        list(
            VirtualMachineInstance.get(
                client=admin_client,
                label_selector="kubevirt.io/outdatedLauncherImage",
            )
        )
    )
    assert vmis_with_outdated_label > 0, "There is no outdated vms"
    return vmis_with_outdated_label


@pytest.fixture(scope="session")
def kubevirt_resource_outdated_vmi_workloads_count(kubevirt_resource_scope_session):
    return kubevirt_resource_scope_session.instance.status.outdatedVirtualMachineInstanceWorkloads


@pytest.fixture(scope="session")
def namespace_for_outdated_vm_upgrade(admin_client, unprivileged_client):
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name="test-outdated-vm-ns")
