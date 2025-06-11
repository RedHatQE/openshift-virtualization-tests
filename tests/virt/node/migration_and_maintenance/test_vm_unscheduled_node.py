import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from utilities.constants import TIMEOUT_20SEC
from utilities.infra import get_node_selector_dict, get_node_selector_name
from utilities.virt import (
    node_mgmt_console,
    vm_instance_from_template,
    wait_for_node_schedulable_status,
)


@pytest.fixture()
def unscheduled_node_vm(
    request,
    cluster_cpu_model_scope_function,
    worker_node1,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
    ) as vm:
        yield vm


@pytest.mark.gating
@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.rwx_default_storage
@pytest.mark.parametrize(
    "data_volume_scope_function, unscheduled_node_vm",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                "vm_name": "rhel-node-maintenance",
                "template_labels": RHEL_LATEST_LABELS,
                "start_vm": False,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-4157")
def test_schedule_vm_on_cordoned_node(nodes, data_volume_scope_function, unscheduled_node_vm):
    """Test VM scheduling on a node under maintenance.
    1. Cordon the Node
    2. Once node status is 'Ready,SchedulingDisabled', start a VM (on the
    selected node) and check that VMI phase is 'scheduling'
    3. Uncordon the Node
    4. Verify the VMI phase is still 'scheduling'
    5. Wait for node status to be 'Ready'
    6. Wait for VMI status to be 'Running'
    7. Verify VMI is running on the selected node
    """
    vm_node = [
        node for node in nodes if node.name == get_node_selector_name(node_selector=unscheduled_node_vm.node_selector)
    ][0]
    with node_mgmt_console(node=vm_node, node_mgmt="cordon"):
        wait_for_node_schedulable_status(node=vm_node, status=False)
        unscheduled_node_vm.start()
        unscheduled_node_vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.SCHEDULING, timeout=TIMEOUT_20SEC)
    unscheduled_node_vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.RUNNING)
    vmi_node_name = unscheduled_node_vm.privileged_vmi.virt_launcher_pod.node.name
    assert vmi_node_name == vm_node.name, (
        f"VMI is running on {vmi_node_name} and not on the selected node {unscheduled_node_vm.node_selector}"
    )
