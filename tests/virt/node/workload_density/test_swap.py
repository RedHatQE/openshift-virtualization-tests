import logging
import shlex

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.constants import REMOVE_NEWLINE
from tests.virt.utils import build_node_affinity_dict, start_stress_on_vm
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_20MIN, Images
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures(
        "fail_if_wasp_agent_disabled",
        "wasp_agent_active_and_ready",
        "swap_is_available_on_nodes",
    ),
    pytest.mark.swap,
]

MEMORY_SWAP_MAX_PATH = "/sys/fs/cgroup/memory.swap.max"
MEMORY_SWAP_CURRENT_PATH = "/sys/fs/cgroup/memory.swap.current"

SWAP_LABEL_KEY = "swap-label"
SWAP_LABEL_VALUE = "test"
SWAP_TEST_LABEL = {SWAP_LABEL_KEY: SWAP_LABEL_VALUE}


def wait_virt_launcher_pod_using_swap(vm):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=vm.privileged_vmi.virt_launcher_pod.execute,
        command=shlex.split(f"bash -c 'cat {MEMORY_SWAP_CURRENT_PATH} | {REMOVE_NEWLINE}'"),
        container="compute",
    )
    sample = []
    try:
        for sample in sampler:
            if sample and int(sample) > 0:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"virt-launcher pod does not use swap, current value: {sample}")
        raise


@pytest.fixture(scope="class")
def hco_memory_overcommit_increased(hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "higherWorkloadDensity": {"memoryOvercommitPercentage": 200},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def node_with_min_memory_labeled_for_swap_test(node_with_least_available_memory):
    with ResourceEditor(patches={node_with_least_available_memory: {"metadata": {"labels": SWAP_TEST_LABEL}}}):
        yield


@pytest.fixture(scope="class")
def node_with_max_memory_labeled_for_swap_test(node_with_most_available_memory):
    with ResourceEditor(patches={node_with_most_available_memory: {"metadata": {"labels": SWAP_TEST_LABEL}}}):
        yield


@pytest.fixture(scope="class")
def node_affinity_for_swap_label():
    return build_node_affinity_dict(key=SWAP_LABEL_KEY, values=[SWAP_LABEL_VALUE])


@pytest.fixture(scope="package")
def wasp_agent_daemonset():
    yield DaemonSet(name="wasp-agent", namespace="wasp")


@pytest.fixture(scope="package")
def fail_if_wasp_agent_disabled(wasp_agent_daemonset):
    if not wasp_agent_daemonset.exists:
        pytest.fail(reason="Wasp agent not deployed to cluster")


@pytest.fixture(scope="package")
def wasp_agent_active_and_ready(workers, wasp_agent_daemonset):
    wasp_agent_ds_instance = wasp_agent_daemonset.instance
    desired = wasp_agent_ds_instance.status.desiredNumberScheduled
    ready = wasp_agent_ds_instance.status.numberReady
    assert desired == ready == len(workers), (
        f"Wasp not ready on all nodes. Number of workers: {len(workers)}, \nNumber of ready wasp agent pods: {ready}"
    )


@pytest.fixture(scope="package")
def swap_is_available_on_nodes(workers, workers_utility_pods):
    nodes_without_swap = []
    for node in workers:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        if not pod_exec.exec(command="swapon -s"):
            nodes_without_swap.append(node.name)

    assert not nodes_without_swap, f"SWAP is not active on all worker nodes, Nodes without swap: {nodes_without_swap}"


@pytest.fixture(scope="class")
def calculated_vm_memory_size(available_memory_per_node, node_with_least_available_memory):
    # Due to memory overcommit, the pod created with less memory
    # Increasing memory to be able to overload the node
    return available_memory_per_node[node_with_least_available_memory].bytes * 1.8


@pytest.fixture(scope="class")
def vm_for_swap_usage_test(
    namespace,
    cpu_for_migration,
    calculated_vm_memory_size,
    node_affinity_for_swap_label,
):
    with VirtualMachineForTests(
        name="vm-for-swap-usage-test",
        namespace=namespace.name,
        cpu_model=cpu_for_migration,
        memory_guest=calculated_vm_memory_size,
        image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
        vm_affinity=node_affinity_for_swap_label,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def swap_vm_stress_started(vm_for_swap_usage_test):
    start_stress_on_vm(
        vm=vm_for_swap_usage_test,
        stress_command="nohup stress-ng --vm 1 --vm-bytes 100% --vm-method zero-one -t 30m --vm-keep &> /dev/null &",
    )


@pytest.fixture()
def vm_with_different_qos(request, namespace):
    with VirtualMachineForTests(
        name=request.param["name"],
        namespace=namespace.name,
        memory_requests=Images.Fedora.DEFAULT_MEMORY_SIZE,
        memory_limits=request.param.get("memory_limits"),
        image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.mark.parametrize(
    "vm_with_different_qos",
    [
        pytest.param(
            {"name": "burstable-vm"},
            marks=pytest.mark.polarion("CNV-11530"),
            id="Burstable_QoS",
        ),
        pytest.param(
            {"name": "guaranteed-vm", "memory_limits": Images.Fedora.DEFAULT_MEMORY_SIZE},
            marks=pytest.mark.polarion("CNV-11488"),
            id="Guaranteed_QoS",
        ),
    ],
    indirect=True,
)
def test_swap_status_on_pod(vm_with_different_qos):
    swap_max = vm_with_different_qos.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split(f"bash -c 'cat {MEMORY_SWAP_MAX_PATH} | {REMOVE_NEWLINE}'")
    )
    assert swap_max not in ["0", "max"] if "burstable" in vm_with_different_qos.name else swap_max == "0", (
        f"Incorrect value in {MEMORY_SWAP_MAX_PATH}: {swap_max} for VM {vm_with_different_qos.name}"
    )


class TestVMCanUseSwap:
    @pytest.mark.dependency(name="test_virt_launcher_pod_use_swap")
    @pytest.mark.polarion("CNV-11258")
    def test_virt_launcher_pod_use_swap(
        self,
        hco_memory_overcommit_increased,
        node_with_min_memory_labeled_for_swap_test,
        vm_for_swap_usage_test,
        swap_vm_stress_started,
    ):
        wait_virt_launcher_pod_using_swap(vm=vm_for_swap_usage_test)

    @pytest.mark.dependency(depends=["test_virt_launcher_pod_use_swap"])
    @pytest.mark.polarion("CNV-11259")
    def test_migrate_vm_using_swap(
        self,
        node_with_max_memory_labeled_for_swap_test,
        vm_for_swap_usage_test,
        migration_policy_with_allow_auto_converge,
    ):
        migrate_vm_and_verify(vm=vm_for_swap_usage_test, check_ssh_connectivity=True, timeout=TIMEOUT_20MIN)
