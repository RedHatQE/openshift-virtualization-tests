import logging
from collections import Counter
from contextlib import contextmanager

from ocp_resources.deployment import Deployment
from ocp_resources.kube_descheduler import KubeDescheduler
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.descheduler.constants import (
    DESCHEDULER_DEPLOYMENT_NAME,
    DESCHEDULER_SOFT_TAINT_KEY,
    DESCHEDULING_INTERVAL_120SEC,
)
from tests.virt.utils import is_jira_67515_open
from utilities.constants import (
    TIMEOUT_1MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_15MIN,
    TIMEOUT_20SEC,
    NamespacesNames,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)

LOGGER = logging.getLogger(__name__)

STRATEGIES = "strategies"


class UnexpectedBehaviorError(Exception):
    def __init__(self, error_msg):
        self.error_msg = error_msg

    def __str__(self):
        return f"Unexpected behavior: {self.error_msg}"


class VirtualMachineForDeschedulerTest(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        memory_guest,
        client,
        cpu_model,
        body,
        cpu_cores,
        descheduler_eviction=True,
        node_selector_labels=None,
        vm_affinity=None,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            memory_guest=memory_guest,
            cpu_model=cpu_model,
            body=body,
            cpu_cores=cpu_cores,
            node_selector_labels=node_selector_labels,
            run_strategy=VirtualMachine.RunStrategy.ALWAYS,
            vm_affinity=vm_affinity,
        )
        self.descheduler_eviction = descheduler_eviction

    def to_dict(self):
        super().to_dict()
        metadata = self.res["spec"]["template"]["metadata"]
        metadata.setdefault("annotations", {})
        if self.descheduler_eviction:
            metadata["annotations"]["descheduler.alpha.kubernetes.io/evict"] = "true"


def calculate_vm_deployment(
    available_memory_per_node,
    deployment_size,
    available_nodes,
    percent_of_available_memory,
):
    vm_deployment = {}
    for node in available_nodes:
        vm_deployment[node] = int(
            (available_memory_per_node[node].bytes * percent_of_available_memory) / deployment_size["memory"].bytes
        )

    LOGGER.info(f"calculated vm_deployment: {vm_deployment}")

    return vm_deployment


def wait_vmi_failover(vm, orig_node):
    samples = TimeoutSampler(wait_timeout=TIMEOUT_15MIN, sleep=TIMEOUT_5SEC, func=lambda: vm.vmi.node.name)
    LOGGER.info(f"Waiting for {vm.name} to be moved from node {orig_node.name}")
    try:
        for sample in samples:
            if sample and sample != orig_node.name:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"VM {vm.name} failed to deploy on new node")
        raise


def assert_vms_distribution_after_failover(vms, nodes, all_nodes=True):
    def _get_vms_per_nodes():
        return vms_per_nodes(vms=vm_nodes(vms=vms))

    # Allow the descheduler to cycle multiple times before returning.
    # The value can be affected by high pod counts or load within
    # the cluster which increases the descheduler runtime.
    descheduling_failover_timeout = DESCHEDULING_INTERVAL_120SEC * 3

    if all_nodes:
        LOGGER.info("Verify all nodes have at least one VM running")
    else:
        LOGGER.info("Verify at least one node has a VM running")

    samples = TimeoutSampler(
        wait_timeout=descheduling_failover_timeout,
        sleep=TIMEOUT_5SEC,
        func=_get_vms_per_nodes,
    )
    vms_per_nodes_dict = None
    try:
        for vms_per_nodes_dict in samples:
            vm_counts = [vm_count for vm_count in vms_per_nodes_dict.values() if vm_count]
            if all_nodes and len(vm_counts) == len(nodes):
                LOGGER.info(f"Every node has at least one VM running on it: {vms_per_nodes_dict}")
                return
            elif vm_counts and not all_nodes:
                LOGGER.info(f"There is at least one node with a VM running on it: {vms_per_nodes_dict}")
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Running VMs missing from nodes: {vms_per_nodes_dict}")
        raise


def vms_per_nodes(vms):
    """
    Args:
        vms (dict): dict of VM objects

    Returns:
        dict: keys - node names, values - number of running VMs
    """
    return Counter([node.name for node in vms.values()])


def vm_nodes(vms):
    """
    Args:
        vms (list): list of VM objects

    Returns:
        dict: keys- VM names, keys - running VMs nodes objects
    """
    return {vm.name: vm.vmi.node for vm in vms}


def assert_vms_consistent_virt_launcher_pods(running_vms):
    """Verify VMs virt launcher pods are not replaced (sampled every one minute).
    Using VMs virt launcher pods to verify that VMs are not migrated nor restarted.

    Args:
        running_vms (list): list of VMs
    """

    def _vms_launcher_pod_names():
        return {
            vm.name: vm.vmi.virt_launcher_pod.name
            for vm in running_vms
            if vm.vmi.virt_launcher_pod.status == vm.vmi.virt_launcher_pod.Status.RUNNING
        }

    orig_virt_launcher_pod_names = _vms_launcher_pod_names()
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_1MIN,
        func=_vms_launcher_pod_names,
    )
    try:
        for sample in samples:
            if any([pod_name != orig_virt_launcher_pod_names[vm_name] for vm_name, pod_name in sample.items()]):
                raise UnexpectedBehaviorError(
                    error_msg=f"Some VMs were migrated: {sample} from {orig_virt_launcher_pod_names}"
                )
    except TimeoutExpiredError:
        LOGGER.info("No VMs were migrated.")


def deploy_vms(
    vm_prefix,
    client,
    namespace_name,
    cpu_model,
    vm_count,
    deployment_size,
    descheduler_eviction,
    node_selector_labels=None,
    vm_affinity=None,
):
    vms = []
    for vm_index in range(vm_count):
        vm_name = f"vm-{vm_prefix}-{vm_index}"
        vm = VirtualMachineForDeschedulerTest(
            name=vm_name,
            namespace=namespace_name,
            client=client,
            cpu_cores=deployment_size["cpu"],
            memory_guest=deployment_size["memory"].bytes,
            cpu_model=cpu_model,
            descheduler_eviction=descheduler_eviction,
            body=fedora_vm_body(name=vm_name),
            node_selector_labels=node_selector_labels,
            vm_affinity=vm_affinity,
        )
        vm.deploy()
        vms.append(vm)

    for vm in vms:
        running_vm(vm=vm)

    yield vms

    # delete all VMs simultaneously
    for vm in vms:
        vm.delete()

    for vm in vms:
        # Due to the bug - VM may hang in terminating state, need to remove the finalizer from VMI
        if not vm.wait_deleted() and is_jira_67515_open():
            ResourceEditor(patches={vm.vmi: {"metadata": {"finalizers": []}}}).update()


def verify_at_least_one_vm_migrated(vms, node_before):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_20SEC,
        func=lambda: [vm.vmi.node.name for vm in vms],
    )
    for sample in samples:
        if not all(node_before.name == node for node in sample):
            return sample


@contextmanager
def create_kube_descheduler(admin_client, profiles, profile_customizations):
    with KubeDescheduler(
        name="cluster",
        namespace=NamespacesNames.OPENSHIFT_KUBE_DESCHEDULER_OPERATOR,
        client=admin_client,
        profiles=profiles,
        descheduling_interval_seconds=DESCHEDULING_INTERVAL_120SEC,
        mode="Automatic",
        management_state="Managed",
        profile_customizations=profile_customizations,
    ) as kd:
        deployment = Deployment(
            name=DESCHEDULER_DEPLOYMENT_NAME,
            namespace=NamespacesNames.OPENSHIFT_KUBE_DESCHEDULER_OPERATOR,
            client=admin_client,
        )
        deployment.wait_for_replicas()
        yield kd


def wait_for_overutilized_soft_taint(node, taint_expected, wait_timeout=TIMEOUT_10MIN):
    taint_key = f"{DESCHEDULER_SOFT_TAINT_KEY}/overutilized"
    sampler = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: any(taint_key in taint.values() for taint in node.instance.spec.taints),
    )
    try:
        for sample in sampler:
            if sample == taint_expected:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Soft taint was not {'added' if taint_expected else 'removed'} in time")
        raise


def assert_psi_values_within_threshold(prometheus):
    metric_output = prometheus.query_sampler(query="descheduler:combined_utilization_and_pressure:avg1m")
    psi_values_dict = {item["metric"]["instance"]: float(item["value"][1]) * 100 for item in metric_output}

    # Default deviation threshold is AsymmetricLow, i.e. "average + 10"
    threshold = sum(psi_values_dict.values()) / len(psi_values_dict) + 10
    assert all(percentage < threshold for percentage in psi_values_dict.values()), (
        f"One or more nodes exceeded the threshold '{threshold}': {psi_values_dict}"
    )
