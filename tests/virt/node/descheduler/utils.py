import logging
from collections import Counter

from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.descheduler.constants import (
    DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION,
    DESCHEDULER_SOFT_TAINT_KEY,
)
from utilities.constants.timeouts import (
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_20SEC,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


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
        prefer_no_eviction=False,
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
        self.prefer_no_eviction = prefer_no_eviction

    def to_dict(self):
        super().to_dict()
        if self.prefer_no_eviction:
            metadata = self.res["spec"]["template"]["metadata"]
            metadata.setdefault("annotations", {})
            metadata["annotations"][DESCHEDULER_PREFER_NO_EVICTION_ANNOTATION] = "true"


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


def deploy_vms(
    vm_prefix,
    client,
    namespace_name,
    cpu_model,
    vm_count,
    deployment_size,
    prefer_no_eviction=False,
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
            prefer_no_eviction=prefer_no_eviction,
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
        vm.wait_deleted()


def verify_at_least_one_vm_migrated(vms, node_before):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_20SEC,
        func=lambda: [vm.vmi.node.name for vm in vms],
    )
    for sample in samples:
        if not all(node_before.name == node for node in sample):
            return sample


def wait_for_overutilized_soft_taint(node, taint_expected, wait_timeout=TIMEOUT_10MIN):
    taint_key = f"{DESCHEDULER_SOFT_TAINT_KEY}/overutilized"
    sampler = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: any(taint_key in taint.values() for taint in (node.instance.spec.taints or [])),
    )
    try:
        for sample in sampler:
            if sample == taint_expected:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Soft taint was not {'added' if taint_expected else 'removed'} in time")
        raise


def assert_psi_values_within_threshold(psi_values_dict):
    # Default deviation threshold is AsymmetricLow, i.e. "average + 10"
    # Add 2 for sampling tolerance
    threshold = sum(psi_values_dict.values()) / len(psi_values_dict) + 12
    assert all(percentage < threshold for percentage in psi_values_dict.values()), (
        f"One or more nodes exceeded the threshold '{threshold}': {psi_values_dict}"
    )
