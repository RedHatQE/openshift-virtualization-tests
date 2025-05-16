import time

import pytest
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.job import Job
from ocp_resources.service_account import ServiceAccount
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.utils import get_image_from_csv
from tests.virt.constants import MachineTypesNames
from utilities.constants import TIMEOUT_2MIN, Images
from utilities.infra import add_scc_to_service_account, create_ns
from utilities.virt import VirtualMachineForTests, restart_vm_wait_for_running_vm, running_vm, wait_for_running_vm

KUBEVIRT_API_LIFECYCLE_AUTOMATION = "kubevirt-api-lifecycle-automation"


@pytest.fixture(scope="session")
def kubevirt_api_lifecycle_image_url(csv_related_images_scope_session):
    return get_image_from_csv(
        image_string=KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        csv_related_images=csv_related_images_scope_session,
    )


@pytest.fixture()
def kubevirt_api_lifecycle_automation_job(
    request,
    kubevirt_api_lifecycle_image_url,
    admin_client,
    namespace,
    kubevirt_api_lifecycle_namespace,
):
    params = request.param
    container = {
        "name": KUBEVIRT_API_LIFECYCLE_AUTOMATION,
        "image": kubevirt_api_lifecycle_image_url,
        "imagePullPolicy": "Always",
        "env": [
            {"name": "MACHINE_TYPE_GLOB", "value": params.get("machine_type_glob")},
            {"name": "RESTART_REQUIRED", "value": params.get("restart_required")},
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


@pytest.fixture()
def vm_with_schedulable_machine_type(admin_client, namespace):
    name = "vm-with-schedulable-machine-type"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=admin_client,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        machine_type=MachineTypesNames.pc_q35_rhel8_1,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_unschedulable_machine_type(admin_client, namespace):
    with VirtualMachineForTests(
        name="vm-with-unschedulable-machine-type",
        namespace=namespace.name,
        client=admin_client,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        machine_type=MachineTypesNames.pc_q35_rhel7_4,
    ) as vm:
        vm.start(wait=False)
        time.sleep(60)
        yield vm


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


@pytest.mark.polarion("CNV-11989")
def test_vm_scheduling_based_on_machine_type(
    admin_client, vm_with_schedulable_machine_type, vm_with_unschedulable_machine_type
):
    assert vm_with_schedulable_machine_type.vmi.status == VirtualMachineInstance.Status.RUNNING, (
        f"VM {vm_with_schedulable_machine_type.name} with schedulable machine type is not running"
    )
    assert (
        vm_with_unschedulable_machine_type.instance.status.get("printableStatus")
        == VirtualMachine.Status.ERROR_UNSCHEDULABLE
    ), f"VM {vm_with_unschedulable_machine_type.name} with unschedulable machine type should not be running"


@pytest.mark.usefixtures(
    "kubevirt_api_lifecycle_namespace",
    "kubevirt_api_lifecycle_service_account",
    "kubevirt_api_lifecycle_cluster_role_binding",
)
class TestMachineTypeTransition:
    @pytest.mark.parametrize(
        "kubevirt_api_lifecycle_automation_job",
        [
            pytest.param(
                {
                    "machine_type_glob": "pc-q35-rhel8.*.*",
                    "restart_required": "true",
                },
                marks=pytest.mark.polarion("CNV-11949"),
            ),
        ],
        indirect=True,
    )
    def test_machine_type_transition_with_restart_true(
        self,
        vm_with_schedulable_machine_type,
        machine_type_from_kubevirt_config,
        kubevirt_api_lifecycle_automation_job,
    ):
        wait_for_running_vm(vm=vm_with_schedulable_machine_type)
        assert (
            vm_with_schedulable_machine_type.vmi.instance.spec.domain.machine.type == machine_type_from_kubevirt_config
        ), f"VM {vm_with_schedulable_machine_type.name} should have machine type {machine_type_from_kubevirt_config}"

    @pytest.mark.parametrize(
        "kubevirt_api_lifecycle_automation_job",
        [
            pytest.param(
                {
                    "machine_type_glob": "pc-q35-rhel8.*.*",
                    "restart_required": "false",
                },
                marks=pytest.mark.polarion("CNV-11950"),
            ),
        ],
        indirect=True,
    )
    def test_machine_type_transition_without_restart(
        self,
        vm_with_schedulable_machine_type,
        machine_type_from_kubevirt_config,
        kubevirt_api_lifecycle_automation_job,
    ):
        assert vm_with_schedulable_machine_type.vmi.status == VirtualMachineInstance.Status.RUNNING
        assert (
            vm_with_schedulable_machine_type.vmi.instance.spec.domain.machine.type == MachineTypesNames.pc_q35_rhel8_1
        ), f"VM {vm_with_schedulable_machine_type.name} should have same machine type as before transition"
        restart_vm_wait_for_running_vm(vm=vm_with_schedulable_machine_type, wait_for_interfaces=True)
        assert (
            vm_with_schedulable_machine_type.vmi.instance.spec.domain.machine.type == machine_type_from_kubevirt_config
        ), f"VM {vm_with_schedulable_machine_type.name} should have machine type {machine_type_from_kubevirt_config}"
