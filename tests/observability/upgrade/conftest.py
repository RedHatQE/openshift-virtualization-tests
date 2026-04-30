import logging

import pytest
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities.constants import ES_NONE
from utilities.infra import create_ns, get_node_selector_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def reusable_upgrade_vm(request):
    network_fixtures = ("running_vm_upgrade_a", "running_vm_upgrade_b")
    for fixture_name in network_fixtures:
        if any(fixture_name in item.fixturenames for item in request.session.items):
            LOGGER.info(f"Reusing {fixture_name} from network upgrade tests")
            return request.getfixturevalue(fixture_name)


@pytest.fixture(scope="session")
def vm_with_node_selector_for_upgrade(
    reusable_upgrade_vm, namespace_for_outdated_vm_upgrade, unprivileged_client, worker_node1
):
    if reusable_upgrade_vm:
        yield reusable_upgrade_vm
    else:
        LOGGER.info("Network upgrade tests not collected, creating dedicated VM")
        name = "vm-with-node-selector"
        with VirtualMachineForTests(
            name=name,
            namespace=namespace_for_outdated_vm_upgrade.name,
            body=fedora_vm_body(name=name),
            node_selector=get_node_selector_dict(node_selector=worker_node1.name),
            client=unprivileged_client,
            run_strategy=VirtualMachine.RunStrategy.ALWAYS,
            eviction_strategy=ES_NONE,
        ) as vm:
            running_vm(vm=vm)
            yield vm


@pytest.fixture()
def outdated_vmis_count(admin_client):
    vmis_with_outdated_label = len(
        list(
            VirtualMachineInstance.get(
                client=admin_client,
                label_selector="kubevirt.io/outdatedLauncherImage",
            )
        )
    )
    assert vmis_with_outdated_label > 0, "There are no outdated vms"
    return vmis_with_outdated_label


@pytest.fixture(scope="class")
def kubevirt_resource_outdated_vmi_workloads_count(kubevirt_resource_scope_session):
    return kubevirt_resource_scope_session.instance.status.outdatedVirtualMachineInstanceWorkloads


@pytest.fixture(scope="session")
def namespace_for_outdated_vm_upgrade(admin_client, unprivileged_client):
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name="test-outdated-vm-ns")
