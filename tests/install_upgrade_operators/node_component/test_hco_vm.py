import logging

import pytest
from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine

from tests.install_upgrade_operators.node_component.utils import (
    NODE_PLACEMENT_INFRA,
    NODE_PLACEMENT_WORKLOADS,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_console,
    wait_for_vm_interfaces,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def hco_vm(unprivileged_client, namespace):
    name = "hco-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        wait_for_console(vm=vm)
        yield vm
        vm.stop(wait=True)


@pytest.mark.parametrize(
    "hyperconverged_with_node_placement",
    [
        pytest.param(
            {"infra": NODE_PLACEMENT_INFRA, "workloads": NODE_PLACEMENT_WORKLOADS},
            marks=(pytest.mark.polarion("CNV-5715"),),
        )
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_remove_workload_label_from_node_while_vm_running(
    node_placement_labels, hyperconverged_with_node_placement, hco_vm
):
    node_name = hco_vm.privileged_vmi.node.name
    LOGGER.info(f"Removing workload label from node: {node_name}")
    try:
        with ResourceEditor(patches={hco_vm.privileged_vmi.node: {"metadata": {"labels": {"work-comp": None}}}}):
            LOGGER.info("Workload label removed from node: {node_name} while VM is running as expected")

    except ForbiddenError:
        LOGGER.error(f"Unable to remove workload label from node: {node_name} while vm/workload is present")
        raise
