import pytest
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.job import Job
from ocp_resources.resource import ResourceEditor
from ocp_resources.service_account import ServiceAccount
from ocp_resources.virtual_machine import VirtualMachine

from tests.utils import get_image_from_csv
from tests.virt.constants import MachineTypesNames
from utilities.constants import TIMEOUT_2MIN, Images
from utilities.infra import add_scc_to_service_account, create_ns
from utilities.virt import VirtualMachineForTests, restart_vm_wait_for_running_vm, running_vm, wait_for_running_vm

KUBEVIRT_API_LIFECYCLE_AUTOMATION = "kubevirt-api-lifecycle-automation"
TESTS_CLASS_NAME = "TestMachineTypeTransition"
ERROR_MESSAGE = "VM {} should have machine type {}, current machine type: {}"


@pytest.fixture(scope="session")
def kubevirt_api_lifecycle_image_url(csv_related_images_scope_session):
    return get_image_from_csv(
        image_string=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        csv_related_images=csv_related_images_scope_session,
    )


@pytest.fixture()
def kubevirt_api_lifecycle_automation_job(
    request,
    admin_client,
    namespace,
    kubevirt_api_lifecycle_image_url,
    kubevirt_api_lifecycle_namespace,
):
    container = {
        "name": KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        "image": kubevirt_api_lifecycle_image_url,
        "imagePullPolicy": "Always",
        "env": [
            {"name": "MACHINE_TYPE_GLOB", "value": "pc-q35-rhel8.*.*"},
            {"name": "RESTART_REQUIRED", "value": request.param["restart_required"]},
            {"name": "NAMESPACE", "value": namespace.name},
        ],
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "privileged": False,
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
    }

    with Job(
        name=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        namespace=kubevirt_api_lifecycle_namespace.name,
        client=admin_client,
        containers=[container],
        service_account=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        restart_policy="Never",
        backoff_limit=0,
    ) as job:
        job.wait_for_condition(
            condition=Job.Condition.COMPLETE,
            status=Job.Condition.Status.TRUE,
            timeout=TIMEOUT_2MIN,
        )
        yield job


@pytest.fixture(scope="session")
def kubevirt_api_lifecycle_namespace(admin_client):
    yield from create_ns(name=KUBEVIRT_API_LIFECYCLE_AUTOMATION, admin_client=admin_client)


@pytest.fixture(scope="session")
def kubevirt_api_lifecycle_service_account(kubevirt_api_lifecycle_namespace):
    with ServiceAccount(name=KUBEVIRT_API_LIFECYCLE_AUTOMATION, namespace=kubevirt_api_lifecycle_namespace.name) as sa:
        add_scc_to_service_account(
            namespace=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
            scc_name="privileged",
            sa_name=sa.name,
        )
        yield sa


@pytest.fixture(scope="session")
def kubevirt_api_lifecycle_cluster_role_binding(admin_client, kubevirt_api_lifecycle_service_account):
    with ClusterRoleBinding(
        name=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        cluster_role="cluster-admin",
        client=admin_client,
        subjects=[
            {
                "kind": ServiceAccount.kind,
                "name": KUBEVIRT_API_LIFECYCLE_AUTOMATION,
                "namespace": KUBEVIRT_API_LIFECYCLE_AUTOMATION,
            }
        ],
    ) as crb:
        yield crb


@pytest.fixture(scope="class")
def vm_with_schedulable_machine_type(unprivileged_client, namespace):
    with VirtualMachineForTests(
        name="vm-with-schedulable-machine-type",
        namespace=namespace.name,
        client=unprivileged_client,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        machine_type=MachineTypesNames.pc_q35_rhel8_1,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def vm_with_schedulable_machine_type_running_after_job(
    vm_with_schedulable_machine_type, kubevirt_api_lifecycle_automation_job
):
    running_vm(vm=vm_with_schedulable_machine_type)
    yield vm_with_schedulable_machine_type


@pytest.fixture()
def restarted_vm_with_schedulable_machine_type(vm_with_schedulable_machine_type):
    restart_vm_wait_for_running_vm(vm=vm_with_schedulable_machine_type)
    yield vm_with_schedulable_machine_type


@pytest.fixture()
def vm_with_unschedulable_machine_type(unprivileged_client, namespace):
    with VirtualMachineForTests(
        name="vm-with-unschedulable-machine-type",
        namespace=namespace.name,
        client=unprivileged_client,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        machine_type=MachineTypesNames.pc_q35_rhel7_4,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def update_vm_machine_type(vm_with_schedulable_machine_type):
    ResourceEditor({
        vm_with_schedulable_machine_type: {
            "spec": {"template": {"spec": {"domain": {"machine": {"type": MachineTypesNames.pc_q35_rhel8_1}}}}}
        }
    }).update()
    restart_vm_wait_for_running_vm(vm=vm_with_schedulable_machine_type, wait_for_interfaces=True)


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
        f"Node {nodes_without_machine_type_label} does not have 'machine-type' label"
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
            vm_with_schedulable_machine_type_running_after_job.name,
            machine_type_from_kubevirt_config,
            vm_machine_type,
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
            vm_with_schedulable_machine_type_running_after_job.name,
            MachineTypesNames.pc_q35_rhel8_1,
            machine_type_before_restart,
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
            restarted_vm_with_schedulable_machine_type.name,
            machine_type_from_kubevirt_config,
            machine_type_after_restart,
        )
