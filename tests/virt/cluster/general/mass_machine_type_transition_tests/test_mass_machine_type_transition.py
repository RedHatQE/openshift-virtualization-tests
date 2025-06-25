import pytest
from ocp_resources.virtual_machine import VirtualMachine

from tests.virt.constants import MachineTypesNames
from utilities.virt import wait_for_running_vm

TESTS_CLASS_NAME = "TestMachineTypeTransition"
ERROR_MESSAGE = (
    "VM {vm_name} should have machine type {expected_machine_type}, current machine type: {current_machine_type}"
)


@pytest.mark.polarion("CNV-11948")
def test_nodes_have_machine_type_labels(workers):
    """
    Verify that nodes have machine type labels.
    """
    nodes_without_machine_type_label = [
        node.name
        for node in workers
        if not any(label.startswith("machine-type.node.kubevirt") for label in node.labels.keys())
    ]
    assert not nodes_without_machine_type_label, (
        f"Nodes {nodes_without_machine_type_label} does not have 'machine-type' label"
    )


@pytest.mark.polarion("CNV-12003")
def test_vm_with_unschedulable_machine_type_fails_to_schedule(vm_with_unschedulable_machine_type):
    vm_with_unschedulable_machine_type.wait_for_specific_status(status=VirtualMachine.Status.ERROR_UNSCHEDULABLE)


class TestMachineTypeTransition:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::vm_running_with_schedulable_machine_type")
    @pytest.mark.polarion("CNV-11989")
    def test_vm_running_with_schedulable_machine_type(
        self,
        vm_with_schedulable_machine_type,
    ):
        wait_for_running_vm(vm=vm_with_schedulable_machine_type)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::vm_running_with_schedulable_machine_type"])
    @pytest.mark.usefixtures(
        "kubevirt_api_lifecycle_namespace",
        "kubevirt_api_lifecycle_service_account",
        "kubevirt_api_lifecycle_cluster_role_binding",
    )
    @pytest.mark.parametrize(
        "kubevirt_api_lifecycle_automation_job",
        [
            pytest.param(
                {
                    "restart_required": "true",
                },
                marks=[
                    pytest.mark.polarion("CNV-11949"),
                ],
            ),
        ],
        indirect=True,
    )
    def test_machine_type_transition_with_restart_true(
        self,
        machine_type_from_kubevirt_config,
        vm_with_schedulable_machine_type_running_after_job,
    ):
        vm_machine_type = vm_with_schedulable_machine_type_running_after_job.vmi.instance.spec.domain.machine.type

        assert vm_machine_type == machine_type_from_kubevirt_config, ERROR_MESSAGE.format(
            vm_name=vm_with_schedulable_machine_type_running_after_job.name,
            expected_machine_type=machine_type_from_kubevirt_config,
            current_machine_type=vm_machine_type,
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::machine_type_transition_without_restart",
        depends=[f"{TESTS_CLASS_NAME}::vm_running_with_schedulable_machine_type"],
    )
    @pytest.mark.parametrize(
        "kubevirt_api_lifecycle_automation_job",
        [
            pytest.param(
                {
                    "restart_required": "false",
                },
                marks=pytest.mark.polarion("CNV-11950"),
            ),
        ],
        indirect=True,
    )
    def test_machine_type_transition_without_restart(
        self,
        machine_type_from_kubevirt_config,
        update_vm_machine_type,
        vm_with_schedulable_machine_type_running_after_job,
    ):
        machine_type_before_restart = (
            vm_with_schedulable_machine_type_running_after_job.vmi.instance.spec.domain.machine.type
        )
        assert machine_type_before_restart == MachineTypesNames.pc_q35_rhel8_1, ERROR_MESSAGE.format(
            vm_name=vm_with_schedulable_machine_type_running_after_job.name,
            expected_machine_type=MachineTypesNames.pc_q35_rhel8_1,
            current_machine_type=machine_type_before_restart,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::machine_type_transition_without_restart"])
    @pytest.mark.polarion("CNV-12004")
    def test_restart_vm_with_machine_type_transition(
        self,
        machine_type_from_kubevirt_config,
        restarted_vm_with_schedulable_machine_type,
    ):
        machine_type_after_restart = restarted_vm_with_schedulable_machine_type.vmi.instance.spec.domain.machine.type
        assert machine_type_after_restart == machine_type_from_kubevirt_config, ERROR_MESSAGE.format(
            vm_name=restarted_vm_with_schedulable_machine_type.name,
            expected_machine_type=machine_type_from_kubevirt_config,
            current_machine_type=machine_type_after_restart,
        )
