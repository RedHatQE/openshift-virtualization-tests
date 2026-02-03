import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from tests.virt.utils import build_node_affinity_dict
from utilities.virt import (
    node_mgmt_console,
    vm_instance_from_template,
    wait_for_node_schedulable_status,
)


@pytest.fixture()
def unscheduled_node_vm(
    request,
    worker_node1,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_function,
):
    with vm_instance_from_template(
        request=request,
        client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
        vm_affinity=build_node_affinity_dict(values=[worker_node1.hostname]),
    ) as vm:
        yield vm


@pytest.mark.gating
@pytest.mark.s390x
@pytest.mark.rwx_default_storage
@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function, unscheduled_node_vm",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
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
def test_schedule_vm_on_cordoned_node(admin_client, worker_node1, unscheduled_node_vm):
    """Test VM scheduling on a node under maintenance.
    1. Cordon the target node specified in the VM's nodeAffinity (worker_node1).
    2. Wait until the node status becomes 'Ready,SchedulingDisabled'.
    3. Start the VM and verify that the VMI phase is 'Scheduling'.
    4. Uncordon the node.
    5. Wait for the node status to return to 'Ready'.
    6. Wait for the VMI phase to become 'Running'.
    7. Verify that the VMI is running on the expected node (worker_node1).
    """

    with node_mgmt_console(admin_client=admin_client, node=worker_node1, node_mgmt="cordon"):
        wait_for_node_schedulable_status(node=worker_node1, status=False)
        unscheduled_node_vm.start()
    unscheduled_node_vm.vmi.wait_for_status(status=VirtualMachineInstance.Status.RUNNING)
    vmi_node_name = unscheduled_node_vm.vmi.node.name
    assert vmi_node_name == worker_node1.name, (
        f"VMI is running on {vmi_node_name} and not on the expected node {worker_node1.name}"
    )
